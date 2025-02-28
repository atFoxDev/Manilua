import asyncio, aiohttp, aiofiles, os, logging, vdf

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
repos = ['ManifestHub/ManifestHub', 'ikun0014/ManifestHub', 'Auiowu/ManifestAutoUpdate', 'tymolu233/ManifestAutoUpdate']

def stack_error(e):
    return f"{type(e).__name__}: {e}"

async def search_game_info(term):
    url = f'https://steamui.com/loadGames.php?search={term}'
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status == 200:
                return (await r.json()).get('games', [])
            log.error("⚠ Failed to retrieve game info")
            return []

async def find_appid_by_name(name):
    games = await search_game_info(name)
    if games:
        print("🔍 Found matching games:")
        for i, g in enumerate(games, 1):
            disp = g['schinese_name'] or g['name']
            print(f"{i}. {disp} (AppID: {g['appid']})")
        choice = input("Select a game number: ")
        if choice.isdigit() and 1 <= int(choice) <= len(games):
            sel = games[int(choice)-1]
            disp = sel['schinese_name'] or sel['name']
            log.info(f"✅ Selected: {disp} (AppID: {sel['appid']})")
            return sel['appid'], disp
    log.error("⚠ No matching game found")
    return None, None

async def get(sha, path, repo):
    urls = [
        f'https://gcore.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://fastly.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://cdn.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://ghproxy.org/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
        f'https://raw.dgithub.xyz/{repo}/{sha}/{path}'
    ]
    retries = 3
    async with aiohttp.ClientSession() as s:
        while retries:
            for url in urls:
                try:
                    async with s.get(url, ssl=False) as r:
                        if r.status == 200:
                            return await r.read()
                        log.error(f'🔄 Fail: {path} - Status: {r.status}')
                except aiohttp.ClientError:
                    log.error(f'🔄 Fail: {path} - Connection error')
            retries -= 1
            log.warning(f'🔄 Retries left: {retries} - {path}')
    log.error(f'🔄 Exceeded retries: {path}')
    return None

async def get_manifest(sha, path, save_dir, repo):
    depots = []
    try:
        if path.endswith('.manifest'):
            sp = os.path.join(save_dir, path)
            if os.path.exists(sp):
                log.warning(f'👋 Manifest exists: {path}')
                return depots
            content = await get(sha, path, repo)
            if content:
                log.info(f'🔄 Manifest downloaded: {path}')
                async with aiofiles.open(sp, 'wb') as f:
                    await f.write(content)
        elif path in ['Key.vdf', 'config.vdf']:
            content = await get(sha, path, repo)
            if content:
                log.info(f'🔄 Key file downloaded: {path}')
                data = vdf.loads(content.decode('utf-8'))
                for depot_id, info in data['depots'].items():
                    depots.append((depot_id, info['DecryptionKey']))
    except Exception as e:
        log.error(f'Processing failed: {path} - {stack_error(e)}')
        raise
    return depots

async def download_and_process(app_id, game):
    app_id = list(filter(str.isdecimal, app_id.strip().split('-')))[0]
    save_dir = f'[{app_id}]{game}'
    os.makedirs(save_dir, exist_ok=True)
    for repo in repos:
        log.info(f"🔍 Searching repo: {repo}")
        url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
        async with aiohttp.ClientSession() as s:
            async with s.get(url, ssl=False) as r:
                data = await r.json()
                if 'commit' in data:
                    sha = data['commit']['sha']
                    tree_url = data['commit']['commit']['tree']['url']
                    date = data['commit']['commit']['author']['date']
                    async with s.get(tree_url, ssl=False) as r2:
                        tree = (await r2.json()).get('tree', [])
                        depots = []
                        for key in ['Key.vdf', 'config.vdf']:
                            res = await get_manifest(sha, key, save_dir, repo)
                            if res:
                                depots.extend(res)
                                break
                        for item in tree:
                            if item['path'].endswith('.manifest'):
                                depots.extend(await get_manifest(sha, item['path'], save_dir, repo))
                        if depots:
                            log.info(f'✅ Last update: {date}')
                            log.info(f'✅ Stored: {app_id} in {repo}')
                            return depots, save_dir
        log.warning(f"⚠ Not in repo {repo}. Moving on...")
    log.error(f'⚠ Manifest download failed for: {app_id} in all repos')
    return [], save_dir

def parse_vdf_to_lua(depots, appid, save_dir):
    lines = [f'addappid({appid})']
    for d, key in depots:
        lines.append(f'addappid({d},1,"{key}")')
        for mf in os.listdir(save_dir):
            if mf.startswith(f"{d}_") and mf.endswith(".manifest"):
                manifest_id = mf[len(d)+1:-9]
                lines.append(f'setManifestid({d},"{manifest_id}",0)')
    return "\n".join(lines)

async def main():
    inp = input("Enter appid or game name: ").strip()
    appid, game = await find_appid_by_name(inp)
    if not appid:
        print("No matching game found. Try again.")
        return
    depots, sd = await download_and_process(appid, game)
    if depots:
        lua_script = parse_vdf_to_lua(depots, appid, sd)
        with open(os.path.join(sd, f'{appid}.lua'), 'w', encoding='utf-8') as f:
            f.write(lua_script)
        print(f"Unlock file for {game} generated!")
        print(f"Drag all files in {sd} onto the steamtools window")
        print(f"Then close Steam as prompted & reopen to play {game}")

if __name__ == "__main__":
    while True:
        asyncio.run(main())
        print("\nRestarting...\n")
