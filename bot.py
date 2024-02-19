import zipfile,rarfile,py7zr,os,time,hashlib,urllib.parse,aiohttp,aiofiles,shutil,multivolumefile,re,platform,shlex,asyncio,subprocess,mimetypes,sqlite3
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityUrl
from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import Image
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from datetime import datetime
from thumb_gen import Generator
from dotenv import load_dotenv

load_dotenv(override=True)

LOGFILE_DIR = os.path.join(os.getcwd(), 'logs')
CONN = sqlite3.connect('database.db')
IS_WIN = platform.system()=='Windows'
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
STRING_SESSION = os.getenv('STRING_SESSION')
BASE_DIR = os.getenv('BASE_DIR')

bot = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

def db_get(key, default=None):
    try:
        cursor = CONN.cursor()
        cursor.execute('SELECT value FROM key_values WHERE key=?', (key,))
        return cursor.fetchone()[0]
    except:
        return default
def db_put(key, value):
    cursor = CONN.cursor()
    cursor.execute('''
CREATE TABLE IF NOT EXISTS key_values (
    key CHAR PRIMARY KEY,
    value TEXT
)
''')
    cursor.execute('INSERT OR REPLACE INTO key_values (key, value) VALUES (?, ?)', (key, value))
    CONN.commit()
def human_time_to_seconds(human_time):
    return (datetime.strptime(human_time, "%H:%M:%S.%f") - datetime(1900, 1, 1)).total_seconds()
def seconds_to_human_time(sec): 
    hrs = sec // 3600
    sec %= 3600
    mins = sec // 60
    sec %= 60
    return "%02d:%02d:%02d" % (hrs, mins, sec) 
def check(log_file):
    try:
        with open(log_file, 'r') as file:
            content = file.read()
        duration_match = re.search(r"Duration: (.*?), start:", content)
        raw_duration = duration_match.group(1)
        time_matches = re.findall(r"time=(.*?) bitrate", content)
        raw_time = time_matches[-1]
        fraction = human_time_to_seconds(raw_time) / human_time_to_seconds(raw_duration)
        progress = progress_bar(round(fraction * 100, 2))
        status = f"**Converting**: {progress}\n**Duration**: {raw_duration}\n**CurrentTime**: {raw_time}"
        return status
    except Exception as e:
        print(repr(e))
        return ''
async def show_ffmpeg_status(input_file_path, output_file_path, msg, codec_copy=True):
    if not os.path.isdir(LOGFILE_DIR):
        os.makedirs(LOGFILE_DIR)
    filename = os.path.basename(input_file_path)
    logfile = os.path.join(LOGFILE_DIR, filename+fileNameHash(input_file_path)+'.log')
    cmd = ['python' if IS_WIN else 'python3', 'converter.py', shlex.quote(input_file_path), shlex.quote(output_file_path), shlex.quote(logfile), '1' if codec_copy else '0']
    if IS_WIN:
        subprocess.Popen(cmd, shell=True, stdin=None, stdout=None, stderr=None, close_fds=True)
    else:
        os.system(' '.join(cmd)+" 1> /dev/null 2>&1 & ")
    await asyncio.sleep(10)
    start_time = time.time()
    last = ''
    last_edit_time = start_time
    while os.path.isfile(logfile):
        status = check(logfile)
        if last_edit_time+5 < time.time() and last != status:
            elapsed = seconds_to_human_time(time.time()-start_time)
            await msg.edit(f'**Filename**: {filename}\n{status}\n**Elapsed**: {elapsed}')
            last = status
            last_edit_time = time.time()
        await asyncio.sleep(2)
def find_all_urls(message):
    ret = list()
    if message.entities is None:
        return ret
    for entity in message.entities:
        if type(entity) == MessageEntityUrl:
            url = message.text[entity.offset:entity.offset+entity.length]
            if url.startswith('http://') or url.startswith('https://'):
                ret.append(url)
            else:
                ret.append('http://'+url)
    return ret
def parse_header(header):
    header = header.split(';', 1)
    if len(header)==1:
        return header[0].strip(), {}
    params = [p.split('=') for p in header[1].split(';')]
    return header[0].strip(), {key[0].strip(): key[1].strip('" ') for key in params}
async def get_url(session, url, event, resumable, custom_filename):
    current = 0
    last = 0
    last_edited_time = 0
    file_org_name = os.path.basename(urllib.parse.urlparse(url).path)
    file_name = ""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Microsoft Edge";v="117\', "Not;A=Brand";v="8\', "Chromium";v="117"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1'
    }
    if resumable:
        info = await session.head(url, headers=headers)
        speeddl_url = 'https://speeddl.honar.workers.dev/?durl={}'.format(urllib.parse.quote(url, safe=''))
        speeddl_info = await session.head(speeddl_url)
        total = int(info.headers.get('content-length', 0)) or None
        speedl_total = int(speeddl_info.headers.get('content-length', 0)) or None
        url = speeddl_url if total==speedl_total else url
    start_time = time.time()
    async with session.get(url, headers=headers, verify_ssl=False) as response:
        server_filename = parse_header(response.headers.get('content-disposition', ''))[1].get('filename', None)
        total = int(response.headers.get('content-length', 0)) or None
        if custom_filename is not None:
            file_org_name = custom_filename
        elif server_filename:
            file_org_name = server_filename
        if len(file_org_name) > 250:
            file_org_name = hashlib.md5(file_org_name.encode()).hexdigest()
        file_name = os.path.join(BASE_DIR, file_org_name)
        async with aiofiles.open(file_name, 'wb') as file:
            async for chunk in response.content.iter_chunked(1024):
                await file.write(chunk)
                current += len(chunk)
                percentage = 0 if total is None else round(current/total*100, 2)
                if last+2 < percentage and last_edited_time+5 < time.time():
                    await event.edit("**Downloading**: {}\n**FileName**: {}\n**Size**: {}\n**Downloaded**: {}\n**ElapsedTime**: {}".format(
                        progress_bar(percentage), file_org_name, humanify(total), humanify(current), seconds_to_human_time(time.time()-start_time))
                    )
                    last = percentage
                    last_edited_time = time.time()
    if os.path.isfile(file_name):
        await event.edit(f'file {file_org_name} downloaded successful!', buttons=[goto('file', file_org_name), main_keybtn])
        return file_name
    await event.edit("Error\nSomething went wrong ..")
async def dl_file(url, event, resumable=True, custom_filename=None):
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        return await get_url(session, url, event, resumable, custom_filename)
def is_video(file_path, use_hachoir=True):
    if not use_hachoir:
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is not None:
            return 'video/' in mime_type
    parser = createParser(file_path)
    if parser:
        metadata = extractMetadata(parser)
        if metadata and 'MIME type: video' in str(metadata):
            return True
    return False
def extract_file(inputFile, outputFolder, password=None):
    if inputFile.endswith('.zip'):
        with zipfile.ZipFile(inputFile, 'r') as zip_ref:
            if password is not None:
                zip_ref.setpassword(password)
            zip_ref.extractall(outputFolder)
    elif inputFile.endswith('.rar'):
        with rarfile.RarFile(inputFile, 'r') as rar_ref:
            if password is not None:
                rar_ref.setpassword(password)
            rar_ref.extractall(outputFolder)
    elif inputFile.endswith('.7z'):
        with py7zr.SevenZipFile(inputFile, 'r', password=password) as seven_zip_ref:
            seven_zip_ref.extractall(outputFolder)
    elif inputFile.endswith(('.7z.001', '.7z.0001')):
        with multivolumefile.open(inputFile.rsplit('.7z', 1)[0]+'.7z', mode='rb') as target_archive:
            with py7zr.SevenZipFile(target_archive, 'r', password=password) as seven_zip_ref:
                seven_zip_ref.extractall(outputFolder)
    else:
        raise Exception("Unknown file format")
def generate_thumbnail(video_path, thumbnail_path, time_sec=0.5):
    clip = VideoFileClip(video_path)
    frame = clip.get_frame(time_sec)
    clip.close()
    thumbnail = Image.fromarray(frame)
    thumbnail.save(thumbnail_path)
def humanify(byte_size):
    siz_list = ['KB', 'MB', 'GB']
    for i in range(len(siz_list)):
        if byte_size/1024**(i+1) < 1024:
            return "{} {}".format(round(byte_size/1024**(i+1), 2), siz_list[i])
def progress_bar(percentage):
    prefix_char = '█'
    suffix_char = '▒'
    progressbar_length = 10
    prefix = round(percentage/progressbar_length) * prefix_char
    suffix = (progressbar_length-round(percentage/progressbar_length)) * suffix_char
    return "{}{} {}%".format(prefix, suffix, percentage)
class TimeKeeper:
    last = 0
    last_edited_time = 0
async def prog_callback(upordown, current, total, event, file_org_name, tk):
    percentage = round(current/total*100, 2)
    if tk.last+2 < percentage and tk.last_edited_time+5 < time.time():
        await event.edit("{}loading {}\nFile Name: {}\nSize: {}\n{}loaded: {}".format(upordown, progress_bar(percentage), file_org_name, humanify(total), upordown, humanify(current)))
        tk.last = percentage
        tk.last_edited_time = time.time()
async def upload_and_send(event, msg, uploadFilePath, uploadFileName, caption, force_document=False):
    tk = TimeKeeper()
    file = await bot.upload_file(
        uploadFilePath,
        progress_callback=lambda c,t:prog_callback('Up',c,t,msg,uploadFileName,tk),
    )
    try:
        if is_video(uploadFilePath):
            generate_thumbnail(uploadFilePath, f'{uploadFilePath}.jpg')
    except Exception as e:
        print(repr(e))
    if force_document:
        await bot.send_file(
            event.chat,
            file=file,
            caption=caption,
            force_document=True,
            link_preview=False
        )
    else:
        await bot.send_file(
            event.chat,
            file=file,
            thumb=f'{uploadFilePath}.jpg' if os.path.isfile(f'{uploadFilePath}.jpg') else None,
            caption=caption,
            supports_streaming=True,
            link_preview=False
        )
    if os.path.isfile(f'{uploadFilePath}.jpg'):
        os.unlink(f'{uploadFilePath}.jpg')
def fileNameHash(fileName):
    return hashlib.md5(fileName.encode()).hexdigest()[:16]
def gen_hash_list(list_or_dict):
    if type(list_or_dict) == list:
        return {fileNameHash(k): k for k in list_or_dict}
    elif type(list_or_dict) == dict:
        return {fileNameHash(list_or_dict[k]): [k,list_or_dict[k]] for k in list_or_dict}
def dirfiles(dirPath):
    return gen_hash_list(os.listdir(dirPath))
def get_tree(dirPath):
    tree = {}
    for root, dirs, files in os.walk(dirPath):
        for file in files:
            tree[file] = os.path.join(root, file)
    return gen_hash_list(tree)
def make_pages(buttons, prefix, curr_page='1', page_size=6):
    curr_page = int(curr_page)
    pages = [buttons[i:i + page_size] for i in range(0, len(buttons), page_size)]
    keyboard = pages[curr_page-1]
    prev_nxt = []
    if 1 < curr_page:
        prev_nxt.append(Button.inline('⏪ prev', data='{}{}'.format(prefix, curr_page-1)))
    if curr_page < len(pages)-1:
        prev_nxt.append(Button.inline('next ⏩', data='{}{}'.format(prefix, curr_page+1)))
    if len(prev_nxt)!=0:
        keyboard.append(prev_nxt)
    return keyboard
async def mainPage(scanPath, event, page=1, edit=True, page_size=6):
    files = dirfiles(scanPath)
    if len(files) == 0:
        if edit:
            await event.edit('no files')
            return
        await event.respond('no files')
        return
    buttons = []
    for file in files:
        fpath = os.path.join(BASE_DIR, files[file])
        text = '{} {}'.format(get_icon(fpath), btntext(db_get(files[file], files[file])))
        buttons.append(goto('dir' if os.path.isdir(fpath) else 'file', files[file], text))
    keyboard = make_pages(buttons, 'gotopage:', page)
    keyboard.append([Button.inline('🚫 Delete all 🚫', data='deleteall:deleteall')])
    keyboard.append([Button.inline('📤 Upload all files 📤', data='uploadall:uploadall')])
    if edit:
        await event.edit("Select a file:", buttons=keyboard)
        return
    await event.respond("Select a file:", buttons=keyboard)
async def make_dir_btns(event, dirname, page=1, edit=True):
    all_files_n_p = get_tree(os.path.join(BASE_DIR, dirname))
    buttons = [
    [
        Button.inline(
            btntext(all_files_n_p[file][0]),
            data=f"dirfile:{dirname}-{file}"
        ),
        Button.inline(
            '❌',
            data=f"deldirfilepage:{dirname}-{file}-{page}"
        )
    ]
    for file in all_files_n_p]
    keyboard = []
    if len(all_files_n_p) > 0:
        keyboard = make_pages(buttons, f'dirpage:{dirname}-', page)
    dirhash = fileNameHash(dirname)
    keyboard.append([Button.inline('upload all 📤', data=f"uploadalldir:{dirhash}")])
    keyboard.append([Button.inline('delete this folder 🗑', data=f"delete:{dirhash}")])
    keyboard.append(main_keybtn)
    text = '🗂 folder: {}\n🔢 file count: {}'.format(db_get(dirname, dirname), len(all_files_n_p))
    if edit:
        await event.edit(text, buttons=keyboard)
    else:
        await event.respond(text, buttons=keyboard)
def goto(file_or_dir, name, text=''):
    text = text if text!='' else f'Go to {file_or_dir}'
    if file_or_dir=='file':
        name = fileNameHash(name)
    return [Button.inline(text, data=f"{file_or_dir}:{name}")]
def get_icon(fullPath):
    if os.path.isdir(fullPath):
        return '🗂'
    mime_type, _ = mimetypes.guess_type(fullPath)
    if fullPath.endswith(('.zip', '.rar', '.7z', '.7z.001', '.7z.0001')):
        return '🗜'
    if not mime_type:
        return '🗄'
    elif 'video/' in mime_type:
        return '🎞'
    elif 'audio/' in mime_type:
        return '🎧'
    elif 'image/' in mime_type:
        return '🖼'
    return '🗄'
def btntext(txt, maxlen=30):
    return txt if len(txt)<maxlen else txt[:maxlen-4]+'...'
def gen_thumbs(fileName):
    thumb_dir = os.path.join(os.getcwd(), 'thumbs')
    if not os.path.isdir(thumb_dir):
        os.makedirs(thumb_dir)
    Generator(fileName, output_path=thumb_dir, imgCount=16, columns=4).run()
    return os.path.join(thumb_dir, '{}.jpg'.format(os.path.basename(fileName).rsplit('.', 1)[0]))

@bot.on(events.NewMessage())
async def check_media(event):
    if not os.path.isdir(BASE_DIR):
        os.makedirs(BASE_DIR)
    if event.message.file:
        tk = TimeKeeper()
        msg = await event.respond('wait..')
        file = await event.message.download_media(BASE_DIR, progress_callback=lambda c,t:prog_callback('Down',c,t,msg,event.message.file.name,tk))
        await msg.edit('file download complete ✅', buttons=[goto('file', os.path.basename(file)), main_keybtn])
        raise events.StopPropagation
@bot.on(events.NewMessage(pattern='^[^/]'))
async def check_links(event):
    try:
        urls = find_all_urls(event.message)
        if len(urls) == 0:
            return
        msg = await event.respond('wait...')
        for url in urls:
            await dl_file(url.replace('_'*5, ''), msg, not (event.message.text.startswith('.d') or '_'*5 in url))
        raise events.StopPropagation
    except Exception as e:
        await event.respond(f"Error: {e}")
@bot.on(events.NewMessage(pattern='/ex'))
async def extract_files(event):
    files = dirfiles(BASE_DIR)
    try:
        msg = await event.respond('extracting..')
        cmd = event.message.text.split(' ', 2)
        if cmd[1] not in files:
            await msg.edit("🙃 unrecognized command")
            return
        sel_file_path = os.path.join(BASE_DIR, files[cmd[1]])
        if not os.path.isfile(sel_file_path):
            await msg.edit("🔍 target file dosen't exist")
            return
        expath = os.path.join(BASE_DIR, cmd[1])
        db_put(cmd[1], files[cmd[1]].rsplit('.', 1)[0])
        if os.path.isdir(expath):
            await msg.edit('destination already exists', buttons=[goto('dir', cmd[1], 'switch to folder 🔁'), main_keybtn])
            return
        os.makedirs(expath)
        extract_file(sel_file_path, expath, None if len(cmd)==2 else cmd[2])
        await make_dir_btns(event, cmd[1], 1, False)
        await msg.delete()
    except Exception as e:
        await event.respond(f"Error: {e}")
@bot.on(events.NewMessage(pattern='/rn'))
async def rename_file(event):
    try:
        cmd = event.message.text.split(' ', 2)
        cmd2 = cmd[1].split('-')
        if len(cmd2)==2:
            all_files_n_p = get_tree(os.path.join(BASE_DIR, cmd2[0]))
            target = all_files_n_p[cmd2[1]][1]
            dest = os.path.join(os.path.dirname(target), cmd[2])
            keyboard = [
                goto('dirfile', '{}-{}'.format(cmd2[0], fileNameHash(dest)), 'Go to file'),
                goto('dir', cmd2[0], '◀️ Back to {}'.format(db_get(cmd2[0]))),
                main_keybtn,
            ]
        else:
            files = dirfiles(BASE_DIR)
            target = os.path.join(BASE_DIR, files[cmd[1]])
            dest = os.path.join(BASE_DIR, cmd[2])
            keyboard = [
                goto('file', cmd[2]),
                main_keybtn,
            ]
        os.rename(target, dest)
        await event.respond('file renamed from: {} to: {}'.format(os.path.basename(target), cmd[2]), buttons=keyboard)
    except Exception as e:
        await event.respond(f"Error: {e}")
@bot.on(events.NewMessage(pattern='/files'))
async def list_files(event):
    try:
        await mainPage(BASE_DIR, event, 1, False)
    except Exception as e:
        await event.respond(f"Error: {e}")
@bot.on(events.CallbackQuery())
async def callback_handler(event):
    if not os.path.isdir(BASE_DIR):
        os.makedirs(BASE_DIR)
    files = dirfiles(BASE_DIR)
    sel_filename = None
    try:
        data = event.data.decode('utf-8').split(':', 1)
        data2 = data[1].split('-')
        sel_dir = os.path.join(BASE_DIR, data2[0])
        if os.path.isdir(sel_dir):
            all_files_n_p = get_tree(sel_dir)
            if len(data2) > 1 and data2[1] in all_files_n_p and os.path.isfile(all_files_n_p[data2[1]][1]):
                sel_dir_filename = all_files_n_p[data2[1]][0]
                sel_dir_filepath = all_files_n_p[data2[1]][1]
        if data[0]=='main':
            await mainPage(BASE_DIR, event)
        elif data[0]=='gotopage':
            await mainPage(BASE_DIR, event, data[1])
        elif data[0]=='deldirfilepage':
            if os.path.isfile(sel_dir_filepath):
                os.remove(sel_dir_filepath)
            await make_dir_btns(event, data2[0], data2[2])
        elif data[0]=='dirpage':
            await make_dir_btns(event, data2[0], data2[1])
        elif data[0]=='mvdirfile':
            if os.path.isfile(sel_dir_filepath):
                shutil.move(sel_dir_filepath, BASE_DIR)
            keyboard = [
                goto('dirfile', data[1], '◀️ back')+goto('file', sel_dir_filename),
                main_keybtn,
            ]
            await event.edit(f'file: {sel_dir_filepath} moved to main', buttons=keyboard)
        elif data[0]=='deldirfile':
            if os.path.isfile(sel_dir_filepath):
                os.remove(sel_dir_filepath)
            await event.edit(f'file: {sel_dir_filepath} deleted', buttons=[goto('dir', data2[0], '◀️ Back to {}'.format(db_get(data2[0])))])
        elif data[0] in ('dirfiletomp4c', 'dirfiletomp4copy'):
            await event.edit('wait..')
            await show_ffmpeg_status(sel_dir_filepath, f'{sel_dir_filepath}.mp4', event, data[0]=='dirfiletomp4copy')
            os.remove(sel_dir_filepath)
            await event.edit(f'conversion complete!\noutput file: {sel_dir_filename}.mp4')
        elif data[0] in ('uploaddirfile', 'uploaddirfiledoc'):
            await event.edit('wait..')
            await upload_and_send(event, event, sel_dir_filepath, sel_dir_filepath, sel_dir_filename, data[0]=='uploaddirfiledoc')
            await event.edit(f'file {sel_dir_filename} uploaded ✅', buttons=[main_keybtn])
        elif data[0]=='dirfiletomp4':
            keyboard = [
                [Button.inline('Normal convert (slow)', data=f"dirfiletomp4c:{data[1]}")],
                [Button.inline('Codec copy (fast)', data=f"dirfiletomp4copy:{data[1]}")],
                goto('dirfile', data[1], '◀️ Back'),
                goto('dir', data2[0], '◀️ Back to {}'.format(db_get(data2[0]))),
                main_keybtn
            ]
            await event.edit(f'file: {sel_dir_filename}\n\nconversion options:', buttons=keyboard)
        elif data[0]=='renamedirfile':
            await event.edit(f'file: `{sel_dir_filename}`\nuse following command to rename\n\n`/rn {data[1]} new_name`', buttons=[goto('dir', data2[0], '◀️ Back to {}'.format(db_get(data2[0]))),main_keybtn])
        elif data[0]=='dirfilegenthumbs':
            await event.edit('wait..')
            thumb = gen_thumbs(sel_dir_filepath)
            await event.respond(sel_dir_filename, file=thumb)
            await event.delete()
            await event.respond('thumbnail generated successfully', buttons=[goto('dir', data2[0], '◀️ Back to {}'.format(db_get(data2[0]))),main_keybtn])
        elif data[0]=='dirfile':
            keyboard = [
                [Button.inline('Upload 📤', data=f"uploaddirfile:{data[1]}")],
            ]
            if is_video(sel_dir_filepath, False):
                if sel_dir_filepath.lower().endswith('.mp4'):
                    keyboard.append([Button.inline('Generate thumbnails 🎩', data=f"dirfilegenthumbs:{data[1]}")])
                else:
                    keyboard.append([Button.inline('Convert to .mp4 ♻️', data=f"dirfiletomp4:{data[1]}")])
                keyboard.append([Button.inline('Upload as document 📎', data=f"uploaddirfiledoc:{data[1]}")])
            keyboard.append([Button.inline('rename ✍️', data=f"renamedirfile:{data[1]}")])
            keyboard.append([Button.inline('move to main 📑', data=f"mvdirfile:{data[1]}")])
            keyboard.append([Button.inline('delete ❌', data=f"deldirfile:{data[1]}")])
            keyboard.append(goto('dir', data2[0], '◀️ Back to {}'.format(db_get(data2[0]))))
            await event.edit('{} file: {}\nsize: {}'.format(get_icon(sel_dir_filepath), sel_dir_filepath, humanify(os.path.getsize(sel_dir_filepath))), buttons=keyboard)
        elif data[0]=='deleteall':
            await event.edit('ARE YOU SURE?', buttons=[[Button.inline('Yes', data='deleteallyes:deleteallyes'), Button.inline('No', data='main:main')]])
        elif data[0]=='deleteallyes':
            shutil.rmtree(BASE_DIR)
            await event.edit('ALL FILES DELETED !')
        elif data[0]=='uploadall':
            await event.edit('wait..')
            for item in os.scandir(BASE_DIR):
                if item.is_file():
                    await upload_and_send(event, event, os.path.join(BASE_DIR, item.name), item.name, item.name)
            await event.edit('all files uploaded ✅')
        else:
            if data[1] in files:
                sel_filename = files[data[1]]
                sel_file_path = os.path.join(BASE_DIR, sel_filename)
            else:
                sel_filename = data[1]
                sel_file_path = os.path.join(BASE_DIR, sel_filename)
        if not sel_filename:
            return
        elif not (os.path.isdir(sel_file_path) or os.path.isfile(sel_file_path)):
            await event.edit("file dosen't exists")
        elif data[0]=='file':
            ico = get_icon(sel_file_path)
            keyboard = [
                [Button.inline('Upload 📤', data=f"uploadfile:{data[1]}")],
            ]
            if is_video(sel_file_path, False):
                keyboard.append([Button.inline('Upload as document 📎', data=f"uploadfiledoc:{data[1]}")])
                if sel_filename.lower().endswith('.mp4'):
                    keyboard.append([Button.inline('Generate thumbnails 🎩', data=f"filegenthumbs:{data[1]}")])
                else:
                    keyboard.append([Button.inline('Convert to .mp4 ♻️', data=f"filetomp4:{data[1]}")])
            if sel_filename.endswith(('.zip', '.rar', '.7z', '.7z.001', '.7z.0001')):
                keyboard.append([Button.inline('Extract 🔐', data=f"extract:{data[1]}")])
            keyboard.append([Button.inline('rename ✍️', data=f"rename:{data[1]}")])
            keyboard.append([Button.inline('delete ❌', data=f"delete:{data[1]}")])
            keyboard.append(main_keybtn)
            filesize = humanify(os.path.getsize(sel_file_path))
            await event.edit(f'{ico} file: {sel_filename}\nsize: {filesize}', buttons=keyboard)
        elif data[0]=='dir':
            await make_dir_btns(event, data[1])
        elif data[0] in ('uploadfile', 'uploadfiledoc'):
            event.edit('wait..')
            await upload_and_send(event, event, sel_file_path, sel_filename, sel_filename, data[0]=='uploadfiledoc')
            await event.edit(f'file {sel_filename} uploaded ✅', buttons=[main_keybtn])
        elif data[0]=='filegenthumbs':
            await event.edit('wait..')
            thumb = gen_thumbs(sel_file_path)
            await event.respond(sel_filename, file=thumb)
            await event.delete()
            await event.respond('thumbnail generated successfully', buttons=[main_keybtn])
        elif data[0]=='filetomp4':
            keyboard = [
                [Button.inline('Normal convert (slow)', data=f"filetomp4c:{data[1]}")],
                [Button.inline('Codec copy (fast)', data=f"filetomp4copy:{data[1]}")],
                goto('file', sel_filename, '◀️ Back'),
                main_keybtn,
            ]
            await event.edit(f'file: {sel_filename}\n\nconversion options:', buttons=keyboard)
        elif data[0] in ('filetomp4c', 'filetomp4copy'):
            await event.edit('wait..')
            await show_ffmpeg_status(sel_file_path, f'{sel_file_path}.mp4', event, data[0]=='filetomp4copy')
            os.remove(sel_file_path)
            await event.edit(f'conversion complete!\noutput file: {sel_filename}.mp4')
        elif data[0]=='extract':
            await event.edit(f'file: `{sel_filename}`\nuse following command to extract\n\n`/ex {data[1]} passwd`', buttons=[main_keybtn])
        elif data[0]=='uploadalldir':
            await event.edit('wait..')
            all_files_n_p = get_tree(sel_file_path)
            for file in all_files_n_p:
                await upload_and_send(event, event, all_files_n_p[file][1], all_files_n_p[file][1], all_files_n_p[file][0])
            await event.edit('all files uploaded ✅')
        elif data[0]=='rename':
            await event.edit(f'file: `{sel_filename}`\nuse following command to rename\n\n`/rn {data[1]} new_name`', buttons=[main_keybtn])
        elif data[0]=='delete':
            fof = 'file'
            if os.path.isdir(sel_file_path):
                shutil.rmtree(sel_file_path)
                fof = 'folder'
                sel_filename = db_get(sel_filename, sel_filename)
            elif os.path.isfile(sel_file_path):
                os.remove(sel_file_path)
            await event.edit(f'{fof}: {sel_filename} deleted', buttons=[main_keybtn])
    except Exception as e:
        await event.respond(f"Error: {e}")

main_keybtn = [Button.inline('🔙 Back to files', data="main:main")]
with bot:
    bot.run_until_disconnected()