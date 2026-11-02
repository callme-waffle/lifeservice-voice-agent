"""VOIC-FEAT-010 M15, PRD/SRS VOICE02/VOICE05: manual real API probe.
Run only after explicit approval; uses .env key without printing secrets.
Not collected by pytest; never dials a phone.
"""
import asyncio, json, time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from voice_agent.adapters.live import OpenAILive
from websockets.exceptions import InvalidStatus

def env_values():
    result={}
    for line in (Path(__file__).resolve().parents[3] / '.env').read_text().splitlines():
        key,sep,value=line.strip().removeprefix('export ').partition('=')
        if sep and not key.startswith('#'):
            result[key.strip()]=value.strip().strip('\"\'')
    return result

async def main():
    values=env_values()
    key=values.get('VOICE_AGENT_OPENAI_API_KEY','')
    if not key and values.get('VOICE_AGENT_OPENAI_API_KEY_FILE'):
        key=Path(values['VOICE_AGENT_OPENAI_API_KEY_FILE']).read_text().strip()
    result={'started_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), 'audio_sent':False,'phone_dialed':False}
    start=time.monotonic()
    try:
        if not key:
            raise ValueError('missing key')
        async with asyncio.timeout(15):
            async with OpenAILive(key, values.get('VOICE_AGENT_OPENAI_LIVE_MODEL','gpt-live-1'),values.get('VOICE_AGENT_OPENAI_LIVE_VOICE','marin'),5).open() as connection:
                result['session_started']=True
                await connection.send({'type':'session.close'})
                async with asyncio.timeout(5):
                    while True:
                        event=await connection.receive()
                        if event['type']=='session.closed':
                            result['session_closed']=True
                            seconds=event.get('usage',{}).get('seconds')
                            if isinstance(seconds,(int,float)):
                                result['usage_seconds']=seconds
                            break
        result['outcome']='PASS'
    except InvalidStatus as exc:
        result.update(outcome='FAIL',failure='websocket_http_rejection',http_status=exc.response.status_code)
    except Exception as exc:
        result.update(outcome='FAIL',failure=type(exc).__name__)
    result['elapsed_s']=round(time.monotonic()-start,3)
    Path('/tmp/voice_live_connection_result.json').write_text(json.dumps(result,ensure_ascii=False))
    print(json.dumps(result,ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
