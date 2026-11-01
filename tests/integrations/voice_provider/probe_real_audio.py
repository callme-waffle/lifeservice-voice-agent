"""VOIC-FEAT-010 M15, PRD/SRS VOICE02/VOICE05: manual real API probe.
Run only after explicit approval; uses .env key without printing secrets.
Not collected by pytest; never dials a phone.
"""
import asyncio,audioop,json,time,wave
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from voice_agent.adapters.live import OpenAILive
from voice_agent.core.live import LiveRunner
from voice_agent.contracts.flow import CancellationToken,SingleSessionGate
from voice_agent.contracts.media import AudioChunk,INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import SessionContext,Channel,TaskResult,LiveTranscript,PublicError
from voice_agent.infrastructure.retention import EncryptedRetention

def values():
 result={}
 for line in (Path(__file__).resolve().parents[3] / '.env').read_text().splitlines():
  key,sep,value=line.strip().removeprefix('export ').partition('=')
  if sep and not key.startswith('#'):result[key.strip()]=value.strip().strip('\"\'')
 return result

async def main():
 env=values();key=env.get('VOICE_AGENT_OPENAI_API_KEY','')
 if not key and env.get('VOICE_AGENT_OPENAI_API_KEY_FILE'):key=Path(env['VOICE_AGENT_OPENAI_API_KEY_FILE']).read_text().strip()
 result={'started_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'phone_dialed':False,'business_api_called':False,'output_bytes':0,'transcript_events':0,'delegations':0}
 with wave.open(str(Path(__file__).resolve().parents[1] / 'ht813/fixtures/synthetic_ko_melo_125.wav'),'rb') as w:
  pcm,_=audioop.ratecv(w.readframes(w.getnframes()),2,1,w.getframerate(),16000,None)
 context=SessionContext(uuid4(),Channel.WEB,datetime.now(timezone.utc));token=CancellationToken();gate=SingleSessionGate()
 class Task:
  async def process(self,*args,**kwargs):
   result['delegations']+=1
   return TaskResult('음성 연결 시험입니다. 실제 업무는 실행하지 않았습니다.')
 class Events:
  async def publish(self,event):
   if isinstance(event.payload,LiveTranscript): result['transcript_events']+=1
   if isinstance(event.payload,PublicError):result['public_error']=event.payload.code.value
 async def incoming():
  for index,offset in enumerate(range(0,len(pcm),3200)):
   data=pcm[offset:offset+3200]
   yield AudioChunk(context.session_id,index,data,INTERNAL_AUDIO_FORMAT)
   await asyncio.sleep(len(data)/32000)
 async def output(chunk):
  result['output_bytes']+=len(chunk.data)
  await asyncio.sleep(chunk.duration_ms/1000)
 start=time.monotonic()
 with TemporaryDirectory(prefix='voice-live-real-') as directory:
  root=Path(directory)/'private'
  store=EncryptedRetention(recordings_dir=root/'audio',transcripts_dir=root/'text',audit_path=root/'audit.jsonl',key=b'T'*32)
  await store.start()
  runner=LiveRunner(OpenAILive(key,env.get('VOICE_AGENT_OPENAI_LIVE_MODEL','gpt-live-1'),env.get('VOICE_AGENT_OPENAI_LIVE_VOICE','marin'),5),Task(),gate,store,drain_s=8)
  try:
   async with asyncio.timeout(20):await runner.run(context,incoming(),Events(),output,token)
   result['outcome']='PASS' if result['output_bytes']>0 and runner.last_usage_final else 'FAIL'
  except Exception as exc:result.update(outcome='FAIL',failure=type(exc).__name__)
  finally:
   result['audio_artifacts']=len(list(store.recordings_dir.glob('*.va1')))
   result['text_artifacts']=len(list(store.transcripts_dir.glob('*.va1')))
   result['gate_released']=gate.active_session_id is None
   result['usage_final']=runner.last_usage_final
   result['usage_seconds']=runner.last_usage_seconds
   result['elapsed_s']=round(time.monotonic()-start,3)
   await store.close()
 Path('/tmp/voice_live_audio_result.json').write_text(json.dumps(result,ensure_ascii=False))
 print(json.dumps(result,ensure_ascii=False))
if __name__ == "__main__":
    asyncio.run(main())
