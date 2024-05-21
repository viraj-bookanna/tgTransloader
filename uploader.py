import requests,os,sys,re
from requests_toolbelt.multipart.encoder import MultipartEncoder,MultipartEncoderMonitor

def upload_progress(monitor):
    with open(logfile, 'w') as f:
        f.write(f"{monitor.bytes_read},{monitor.len}")
def upload():
    filename = os.path.basename(filepath)
    filesize = str(os.path.getsize(filepath))
    data = {
        'uid': user_id,
        'id3': 'true',
        'ff': 'true',
        'flowChunkNumber': '1',
        'flowChunkSize': filesize,
        'flowCurrentChunkSize': filesize,
        'flowTotalSize': filesize,
        'flowIdentifier': '{}-{}'.format(filesize, re.sub(r'[^a-zA-Z0-9 ]', '', filename)),
        'flowFilename': filename,
        'flowRelativePath': filename,
        'flowTotalChunks': '1',
        'file': ('ses.jpg', open(filepath, 'rb'), 'application/octet-stream'),
    }
    encoder = MultipartEncoder(fields=data)
    upload_data = MultipartEncoderMonitor(encoder, upload_progress)
    headers = {
        'authority': vserver_host,
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'Content-Type': upload_data.content_type,
        'origin': 'https://video-converter.com',
        'referer': 'https://video-converter.com/',
        'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Microsoft Edge";v="122"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
    }
    response = requests.post(f'https://{vserver_host}/vconv/upload/flow/', verify=0, data=upload_data, headers=headers, allow_redirects=False)
    return response.text

filepath = sys.argv[1]
logfile = sys.argv[2]
with open(logfile, 'w') as file:
    file.write('0,1')
vserver_host = sys.argv[4]
user_id = sys.argv[5]
with open(sys.argv[3], 'w') as file:
    file.write(upload())
os.remove(logfile)
