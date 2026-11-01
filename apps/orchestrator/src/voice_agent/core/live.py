"""Continuous duplex voice session, independent of the on-prem turn pipeline."""
from __future__ import annotations

import asyncio
import audioop
import base64
import time
from dataclasses import asdict

from voice_agent.infrastructure.telemetry import (
    LIVE_AUDIO_SECONDS, LIVE_QUEUE_SECONDS, LIVE_MEDIA_SECONDS, LIVE_FAILURES,
    LIVE_FINALIZATIONS, LIVE_USAGE_SECONDS,
)

from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import (
    EventEnvelope, LiveTranscript, SessionState, SessionStatus, PublicError, ErrorCode,
)


class LiveRunner:
    continuous_input = True

    def __init__(self, transport, task, gate, retention, *, drain_s=5, queue_ms=500,
                 task_timeout_s=120):
        self.transport, self.task, self.gate, self.retention = transport, task, gate, retention
        self.drain_s, self.queue_ms, self.task_timeout_s = drain_s, queue_ms, task_timeout_s
        self.remote_status = "unverified"
        self.last_usage_seconds = None
        self.last_usage_final = False

    async def run(self, context, incoming, events, send_audio, cancel, *, lease=None):
        owned = lease is None
        if owned:
            lease = await self.gate.acquire(context.session_id)
        elif (lease.session_id != context.session_id or lease._gate is not self.gate
              or lease._released):
            raise ValueError("invalid Live session lease")
        work = asyncio.create_task(self._run(context, incoming, events, send_audio, cancel))
        cancellation = asyncio.create_task(cancel.wait())
        try:
            done, _ = await asyncio.wait({work, cancellation}, return_when=asyncio.FIRST_COMPLETED)
            if cancellation in done and not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            else:
                await work
        finally:
            for worker in (work, cancellation):
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(work, cancellation, return_exceptions=True)
            if owned:
                await lease.release()

    async def _run(self, context, incoming, events, send_audio, cancel):
        sequence = 0
        tasks = []
        audio_buffers = {key: bytearray() for key in ("input", "generated", "sent")}
        audio_offsets = dict.fromkeys(audio_buffers, 0)
        transcript_index = 0
        self.last_usage_seconds, self.last_usage_final = None, False

        async def publish(payload):
            nonlocal sequence
            # Reserve the number before yielding to another publisher.
            number, sequence = sequence, sequence + 1
            await events.publish(EventEnvelope(context.session_id, number, payload))

        async def flush(direction, final=False):
            data = audio_buffers[direction]
            while len(data) >= 320_000 or (final and data):
                size = min(len(data), 320_000)
                pcm = bytes(data[:size])
                await self.retention.record_live_audio(
                    context, direction, audio_offsets[direction], pcm,
                )
                del data[:size]
                audio_offsets[direction] += size // 2

        async def record(direction, data):
            LIVE_AUDIO_SECONDS.labels(direction=direction).inc(len(data) / 32000)
            audio_buffers[direction].extend(data)
            await flush(direction)

        await publish(SessionState(SessionStatus.STARTING))
        try:
            async with self.transport.open() as connection:
                self.remote_status = "connected"
                output = asyncio.Queue(maxsize=max(1, self.queue_ms // 20))
                delegations = asyncio.Queue(maxsize=8)
                seen = set()
                fragments = ""
                await publish(SessionState(SessionStatus.LISTENING))

                async def capture():
                    state, expected = None, 0
                    async for chunk in incoming:
                        if (chunk.session_id != context.session_id
                                or chunk.format != INTERNAL_AUDIO_FORMAT
                                or chunk.sequence != expected):
                            raise ValueError("invalid Live input audio")
                        expected += 1
                        await record("input", chunk.data)
                        pcm, state = audioop.ratecv(chunk.data, 2, 1, 16000, 24000, state)
                        async with asyncio.timeout(self.queue_ms / 1000):
                            await connection.send({"type": "session.input_audio.append",
                                                   "audio": base64.b64encode(pcm).decode("ascii")})
                    await connection.send({"type": "session.input_audio.mute"})
                    # Keep output and delegation alive for the configured final drain.
                    await asyncio.sleep(self.drain_s)

                async def playback():
                    index = 0
                    while True:
                        data, queued_at = await output.get()
                        LIVE_QUEUE_SECONDS.set(output.qsize() * .02)
                        await send_audio(AudioChunk(context.session_id, index, data, INTERNAL_AUDIO_FORMAT))
                        LIVE_MEDIA_SECONDS.observe(time.monotonic() - queued_at)
                        await record("sent", data)
                        index += 1

                async def delegate():
                    while True:
                        identifier, snapshot = await delegations.get()
                        if not snapshot.strip():
                            result = "아직 사용자 전사가 없습니다. 요청을 다시 확인하세요. 업무를 실행하지 않았습니다."
                        else:
                            try:
                                async with asyncio.timeout(self.task_timeout_s):
                                    response = await self.task.process(
                                        "다음은 현재 통화의 시간순 전사 조각이며 미완성일 수 있습니다. "
                                        "명확한 요청만 처리하고 불명확하면 확인을 요청하세요.\n" + snapshot,
                                        context, cancel,
                                    )
                                result = response.text
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                result = "업무 처리에 실패했습니다. 성공으로 안내하지 말고 다시 확인하세요."
                        cancel.raise_if_cancelled()
                        # UTF-8 bytes bound also bounds tokenizer worst-case tokens (<500).
                        content = result.encode("utf-8")[:350].decode("utf-8", errors="ignore")
                        if len(result.encode("utf-8")) > 350:
                            content += " [결과 일부; 나머지는 생략됨]"
                        await connection.send({"type": "session.commentary.append",
                                               "delegation_id": identifier, "content": content})

                async def receive():
                    nonlocal fragments, transcript_index
                    state, pending = None, bytearray()
                    while True:
                        event = await connection.receive()
                        kind = event["type"]
                        if kind == "session.output_audio.delta":
                            pcm = base64.b64decode(event["delta"], validate=True)
                            if len(pcm) % 2:
                                raise ValueError("invalid Live audio alignment")
                            converted, state = audioop.ratecv(pcm, 2, 1, 24000, 16000, state)
                            await record("generated", converted)
                            pending.extend(converted)
                            while len(pending) >= 640:
                                # Overflow terminates the call; never silently drop speech.
                                output.put_nowait((bytes(pending[:640]), time.monotonic()))
                                LIVE_QUEUE_SECONDS.set(output.qsize() * .02)
                                del pending[:640]
                        elif kind in ("session.input_transcript.delta", "session.output_transcript.delta"):
                            direction = "input" if "input_transcript" in kind else "output"
                            fragment = LiveTranscript(event["delta"], direction,
                                                      event["start_ms"], event["end_ms"])
                            await self.retention.record_live_text(context, transcript_index, asdict(fragment))
                            transcript_index += 1
                            fragments = (fragments + f"\n[{direction} {fragment.start_ms}:{fragment.end_ms} partial] "
                                         + fragment.text)[-16000:]
                            await publish(fragment)
                        elif kind == "session.delegation.created":
                            item = event["delegation"]
                            if item["target"] != "client":
                                raise ValueError("unexpected delegation target")
                            identifier = item["id"]
                            if identifier not in seen:
                                if len(seen) >= 256:
                                    raise RuntimeError("delegation session limit reached")
                                seen.add(identifier)
                                delegations.put_nowait((identifier, fragments))
                        elif kind in ("session.usage.updated", "session.closed"):
                            usage = event.get("usage", {})
                            if isinstance(usage.get("seconds"), (int, float)):
                                self.last_usage_seconds = usage["seconds"]
                            if kind == "session.closed":
                                self.last_usage_final = True
                                return

                async def expiry():
                    expires = connection.started.get("session", {}).get("expires_at")
                    if isinstance(expires, (int, float)):
                        await asyncio.sleep(max(0, expires - time.time() - 1))
                    else:
                        await asyncio.Future()

                tasks = [asyncio.create_task(coro, name=f"live-{name}") for name, coro in (
                    ("capture", capture()), ("playback", playback()), ("receive", receive()),
                    ("delegation", delegate()), ("cancel", cancel.wait()), ("expiry", expiry()),
                )]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for completed in done:
                        completed.result()
                finally:
                    for pending_task in tasks:
                        pending_task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    # Receiver is stopped before final usage drain; exactly one recv owner.
                    if not self.last_usage_final:
                        try:
                            async with asyncio.timeout(1):
                                await connection.send({"type": "session.close"})
                                while True:
                                    event = await connection.receive()
                                    if event["type"] == "session.closed":
                                        self.last_usage_seconds = event.get("usage", {}).get("seconds")
                                        self.last_usage_final = True
                                        break
                        except Exception:
                            self.last_usage_final = False
                await publish(SessionState(SessionStatus.CANCELLED if cancel.cancelled else SessionStatus.COMPLETED))
        except asyncio.CancelledError:
            cancel.cancel()
            raise
        except Exception as error:
            LIVE_FAILURES.labels(reason="queue_overflow" if isinstance(error, asyncio.QueueFull)
                                 else "timeout" if isinstance(error, TimeoutError) else "unavailable").inc()
            self.remote_status = "unavailable"
            cancel.cancel()
            await publish(PublicError(ErrorCode.UNAVAILABLE, "Live 음성 세션을 계속할 수 없습니다."))
            await publish(SessionState(SessionStatus.FAILED))
            raise
        finally:
            LIVE_QUEUE_SECONDS.set(0)
            LIVE_FINALIZATIONS.labels(status="final" if self.last_usage_final else "incomplete").inc()
            if self.last_usage_seconds is not None:
                LIVE_USAGE_SECONDS.set(self.last_usage_seconds)
            for direction in audio_buffers:
                await flush(direction, final=True)
            if self.remote_status == "connected":
                self.remote_status = "unverified"
