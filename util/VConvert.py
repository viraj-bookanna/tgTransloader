import os,time,asyncio,aiofiles,aiohttp,websockets,re,json,random,string

class ServerConverter:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.headers = {
            'Sec-Ch-Ua': '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Ch-Ua-Mobile': '?0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
            'Accept': '*/*',
            'Origin': 'https://video-converter.com',
            'Sec-Fetch-Site': 'same-site',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://video-converter.com/',
            'Accept-Language': 'en-US,en;q=0.9',
            'Priority': 'u=1, i',
        }
        self.uploading_complete = False
        self.upload_timeout_mins = 20
    def set_upload_timeout(self, time_minutes):
        self.upload_timeout_mins = round(int(time_minutes))
    def set_vserver(self):
        self.vserver_id = 's54'
        self.vserver_host = f'{self.vserver_id}.video-converter.com'
    async def file_sender(self, callback):
        async with aiofiles.open(self.file_path, 'rb') as f:
            current = 0
            chunk = await f.read(64*1024)
            while chunk:
                if callback is not None:
                    current += len(chunk)
                    await callback(current, self.file_size)
                yield chunk
                chunk = await f.read(64*1024)
    async def upload_to_server(self, callback):
        form = [
            ('uid', self.user_id),
            ('id3', 'true'),
            ('ff', 'true'),
            ('flowChunkNumber', '1'),
            ('flowChunkSize', self.file_size),
            ('flowCurrentChunkSize', self.file_size),
            ('flowTotalSize', self.file_size),
            ('flowIdentifier', '{}-{}'.format(self.file_size, re.sub(r'[^a-zA-Z0-9]', '', self.file_name))),
            ('flowFilename', self.file_name),
            ('flowRelativePath', self.file_name),
            ('flowTotalChunks', '1'),
        ]
        boundary = '----WebKitFormBoundary{}'.format(''.join([random.choice(string.ascii_letters+string.digits) for i in range(16)]))
        with aiohttp.MultipartWriter('form-data', boundary=boundary) as mpwriter:
            for item in form:
                part = mpwriter.append(str(item[1]))
                part.set_content_disposition('form-data', name=item[0])
            part = mpwriter.append(self.file_sender(callback), {'content-type': 'application/octet-stream'})
            part.set_content_disposition('form-data', name='file', filename=self.file_name)
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=60*self.upload_timeout_mins)
            ) as session:
                async with session.post(f'https://{self.vserver_host}/vconv/upload/flow/', data=mpwriter, headers=self.headers) as resp:
                    try:
                        return await resp.json()
                    except:
                        response = await resp.text()
                        raise Exception(f'InvalidResponse: {resp.status}\n{response}')
    async def set_session(self):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://video-converter.com/', headers=self.headers) as response:
                self.user_id = response.cookies['uid'].value
            async with session.get(f'https://{self.vserver_host}/socket.io/?EIO=4&transport=polling', headers=self.headers) as response:
                data = await response.text()
        self.session_id = data.split('sid":"')[1].split('"')[0]
    async def poll_msg(self, sockmsg, prefix='42'):
        data = prefix+sockmsg
        async with aiohttp.ClientSession() as session:
            async with session.post(f'https://{self.vserver_host}/socket.io/?EIO=4&transport=polling&sid={self.session_id}', headers=self.headers, data=data) as response:
                return await response.text()
    async def ws_keep_alive(self, websocket):
        while not self.uploading_complete:
            try:
                response = await websocket.recv()
                if response == '2':
                    await websocket.send('3')
                elif response == '3probe':
                    await websocket.send('5')
            except websockets.ConnectionClosedOK as e:
                break
    async def convert_in_server(self, upload_callback=None, convert_callback=None):
        self.set_vserver()
        await self.set_session()
        await self.poll_msg('', '40')
        self.uploading_complete = False
        async with websockets.connect(f'wss://{self.vserver_host}/socket.io/?EIO=4&transport=websocket&sid={self.session_id}') as websocket:
            await websocket.send('2probe')
            keepalive_task = asyncio.create_task(self.ws_keep_alive(websocket))
            res_msg = await self.upload_to_server(upload_callback)
            self.uploading_complete = True
            await asyncio.gather(keepalive_task)
            cmd = {
                "site_id": "vconv",
                "uid": self.user_id,
                "operation_id": '{}_{}_{}'.format(round(time.time()*1000), self.vserver_id, ''.join([random.choice(string.ascii_lowercase+string.digits) for i in range(10)])),
                "action_type": "encode",
                "enable_transfer_proxy": False,
                "country": "LK",
                "tmp_filename": res_msg['tmp_filename'],
                "duration_in_seconds": res_msg['ff']['duration_in_seconds'],
                "acodec": "aac",
                "vcodec": "h265",
                "no_audio": not res_msg['ff']['has_audio_streams'],
                "format_type": "video",
                "format": "mp4",
                "preset": "same",
                "preset_priority": True,
                "lang_id": "en",
                "host": "video-converter.com",
                "protocol": "https:",
                "isp": 0,
                "email": "",
                "app_id": "vconv"
            }
            await websocket.send('42'+json.dumps(["encode",cmd]))
            while 1:
                try:
                    response = await websocket.recv()
                    if response == '2':
                        await websocket.send('3')
                    elif response == '3probe':
                        await websocket.send('5')
                    if response.startswith('42'):
                        sock_msg = json.loads(response[2:])
                        if sock_msg[1]['message_type'] == 'progress':
                            if convert_callback is not None:
                                await convert_callback(sock_msg[1]['progress_value'], 100)
                        elif sock_msg[0]=='encode' and sock_msg[1]['message_type'] == 'final_result':
                            return sock_msg[1]['download_url']
                except websockets.ConnectionClosedOK as e:
                    await event.edit(repr(e))
                    break