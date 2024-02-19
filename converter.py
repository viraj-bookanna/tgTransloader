import os,sys,time,platform,shlex

inFilePath = sys.argv[1]
outFilePath = sys.argv[2]
logFilePath = sys.argv[3]
codec = ' -c copy' if sys.argv[4]=='1' else ''

redir = ('1>NUL 2>{}' if platform.system()=='Windows' else '1> {} 2>&1').format(shlex.quote(logFilePath))
cmd = 'ffmpeg -i {}{} {} {}'.format(shlex.quote(inFilePath), codec, shlex.quote(outFilePath), redir)
os.system(cmd)
time.sleep(3)
os.remove(logFilePath)
