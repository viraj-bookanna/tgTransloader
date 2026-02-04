import os,sys,time,platform,shlex
from dotenv import load_dotenv

load_dotenv(override=True)
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')
inFilePath = sys.argv[1]
outFilePath = sys.argv[2]
logFilePath = sys.argv[3]
codec = ' -c copy' if sys.argv[4]=='1' else ''

redir = ('1>NUL 2>{}' if platform.system()=='Windows' else '1> {} 2>&1').format(shlex.quote(logFilePath))
cmd = f'{FFMPEG_PATH} -i {shlex.quote(inFilePath)}{codec} {shlex.quote(outFilePath)} {redir}'
os.system(cmd)
time.sleep(3)
os.remove(logFilePath)
