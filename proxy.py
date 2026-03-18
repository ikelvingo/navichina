import re
import requests
import traceback
import threading
from queue import Queue
import time
from flask_caching import Cache
from functools import cache
from urllib.parse import unquote
from flask import Flask, abort, request, jsonify, redirect
from cover import download_image_async
from search import get_album_info, get_artist_profile, get_artist_top_songs, get_similar_songs  # type: ignore

app = Flask(__name__)

# ========== 并行查询工具函数 ==========

def parallel_query_artist_info(artist_name, lastfm_api_url, get_artist_profile_func, timeout=9):
    """并行查询艺术家信息（9秒超时）"""
    netease_data = None
    lastfm_data = None
    netease_success = False
    lastfm_success = False
    netease_error = None
    lastfm_error = None
    
    netease_result = Queue()
    lastfm_result = Queue()
    start_time = time.time()
    
    def fetch_netease_data():
        try:
            artist_name_1 = None
            if any(substring in artist_name for substring in [' and ', "&"]):
                sp = re.split(r" and |&", artist_name)
                artist_name_1 = sp[0]
            
            artist_profile = get_artist_profile_func(artist_name)
            if not artist_profile and artist_name_1 is not None:
                artist_profile = get_artist_profile_func(artist_name_1)
            
            if artist_profile:
                netease_result.put(('success', artist_profile['artist']))
            else:
                netease_result.put(('no_data', None))
        except Exception as e:
            netease_result.put(('error', e))
    
    def fetch_lastfm_data():
        try:
            lastfm_response = requests.get(lastfm_api_url, timeout=timeout)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    lastfm_result.put(('success', lastfm_data))
                else:
                    lastfm_result.put(('error', f"Last.fm返回错误: {lastfm_data.get('error')}"))
            else:
                lastfm_result.put(('error', f"Last.fm HTTP错误: {lastfm_response.status_code}"))
        except requests.exceptions.Timeout:
            lastfm_result.put(('timeout', None))
        except Exception as e:
            lastfm_result.put(('error', e))
    
    netease_thread = threading.Thread(target=fetch_netease_data)
    lastfm_thread = threading.Thread(target=fetch_lastfm_data)
    netease_thread.daemon = True
    lastfm_thread.daemon = True
    netease_thread.start()
    lastfm_thread.start()
    
    netease_thread.join(timeout=timeout)
    lastfm_thread.join(timeout=timeout)
    
    elapsed_time = time.time() - start_time
    
    if not netease_result.empty():
        status, result = netease_result.get()
        if status == 'success':
            netease_data = result
            netease_success = True
        elif status == 'timeout':
            netease_error = "Timeout"
        elif status == 'error':
            netease_error = result
    else:
        netease_error = "Timeout"
    
    if not lastfm_result.empty():
        status, result = lastfm_result.get()
        if status == 'success':
            lastfm_data = result
            lastfm_success = True
        elif status == 'timeout':
            lastfm_error = "Timeout"
        elif status == 'error':
            lastfm_error = result
    else:
        lastfm_error = "Timeout"
    
    return (netease_data, lastfm_data, netease_success, lastfm_success, elapsed_time, netease_error, lastfm_error)

def parallel_query_album_info(artist_name, album_name, lastfm_api_url, get_album_info_func, timeout=9):
    """并行查询专辑信息（9秒超时）"""
    netease_data = None
    lastfm_data = None
    netease_success = False
    lastfm_success = False
    netease_error = None
    lastfm_error = None
    
    netease_result = Queue()
    lastfm_result = Queue()
    start_time = time.time()
    
    def fetch_netease_data():
        try:
            album_info = get_album_info_func(artist_name, album_name)
            if album_info:
                netease_result.put(('success', album_info))
            else:
                netease_result.put(('no_data', None))
        except Exception as e:
            netease_result.put(('error', e))
    
    def fetch_lastfm_data():
        try:
            lastfm_response = requests.get(lastfm_api_url, timeout=timeout)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    lastfm_result.put(('success', lastfm_data))
                else:
                    lastfm_result.put(('error', f"Last.fm返回错误: {lastfm_data.get('error')}"))
            else:
                lastfm_result.put(('error', f"Last.fm HTTP错误: {lastfm_response.status_code}"))
        except requests.exceptions.Timeout:
            lastfm_result.put(('timeout', None))
        except Exception as e:
            lastfm_result.put(('error', e))
    
    netease_thread = threading.Thread(target=fetch_netease_data)
    lastfm_thread = threading.Thread(target=fetch_lastfm_data)
    netease_thread.daemon = True
    lastfm_thread.daemon = True
    netease_thread.start()
    lastfm_thread.start()
    
    netease_thread.join(timeout=timeout)
    lastfm_thread.join(timeout=timeout)
    
    elapsed_time = time.time() - start_time
    
    if not netease_result.empty():
        status, result = netease_result.get()
        if status == 'success':
            netease_data = result
            netease_success = True
        elif status == 'timeout':
            netease_error = "Timeout"
        elif status == 'error':
            netease_error = result
    else:
        netease_error = "Timeout"
    
    if not lastfm_result.empty():
        status, result = lastfm_result.get()
        if status == 'success':
            lastfm_data = result
            lastfm_success = True
        elif status == 'timeout':
            lastfm_error = "Timeout"
        elif status == 'error':
            lastfm_error = result
    else:
        lastfm_error = "Timeout"
    
    return (netease_data, lastfm_data, netease_success, lastfm_success, elapsed_time, netease_error, lastfm_error)

def parallel_query_artist_toptracks(artist_name, limit, lastfm_api_url, get_artist_top_songs_func, timeout=9):
    """并行查询艺术家热门歌曲（9秒超时）"""
    netease_data = None
    lastfm_data = None
    netease_success = False
    lastfm_success = False
    netease_error = None
    lastfm_error = None
    
    netease_result = Queue()
    lastfm_result = Queue()
    start_time = time.time()
    
    def fetch_netease_data():
        try:
            top_songs = get_artist_top_songs_func(artist_name, limit)
            if top_songs:
                netease_result.put(('success', top_songs))
            else:
                netease_result.put(('no_data', None))
        except Exception as e:
            netease_result.put(('error', e))
    
    def fetch_lastfm_data():
        try:
            lastfm_response = requests.get(lastfm_api_url, timeout=timeout)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    lastfm_result.put(('success', lastfm_data))
                else:
                    lastfm_result.put(('error', f"Last.fm返回错误: {lastfm_data.get('error')}"))
            else:
                lastfm_result.put(('error', f"Last.fm HTTP错误: {lastfm_response.status_code}"))
        except requests.exceptions.Timeout:
            lastfm_result.put(('timeout', None))
        except Exception as e:
            lastfm_result.put(('error', e))
    
    netease_thread = threading.Thread(target=fetch_netease_data)
    lastfm_thread = threading.Thread(target=fetch_lastfm_data)
    netease_thread.daemon = True
    lastfm_thread.daemon = True
    netease_thread.start()
    lastfm_thread.start()
    
    netease_thread.join(timeout=timeout)
    lastfm_thread.join(timeout=timeout)
    
    elapsed_time = time.time() - start_time
    
    if not netease_result.empty():
        status, result = netease_result.get()
        if status == 'success':
            netease_data = result
            netease_success = True
        elif status == 'timeout':
            netease_error = "Timeout"
        elif status == 'error':
            netease_error = result
    else:
        netease_error = "Timeout"
    
    if not lastfm_result.empty():
        status, result = lastfm_result.get()
        if status == 'success':
            lastfm_data = result
            lastfm_success = True
        elif status == 'timeout':
            lastfm_error = "Timeout"
        elif status == 'error':
            lastfm_error = result
    else:
        lastfm_error = "Timeout"
    
    return (netease_data, lastfm_data, netease_success, lastfm_success, elapsed_time, netease_error, lastfm_error)


# 缓存
cache_dir = '/.cache'
# try:
#     shutil.rmtree(cache_dir)
# except FileNotFoundError:
#     pass

cache = Cache(app, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': cache_dir
})

# 缓存键，解决缓存未忽略参数的情况 COPY FROM LRCAPI


def make_cache_key(*args, **kwargs) -> str:
    path: str = request.path
    args: str = str(hash(frozenset(request.args.items())))
    return path + args


def safe_query_string():
    """返回安全的查询字符串，隐藏敏感信息如api_key"""
    query_dict = request.args.to_dict()
    
    # 需要隐藏的敏感参数
    sensitive_params = ['api_key', 'token', 'password', 'secret', 'key']
    
    safe_dict = {}
    for key, value in query_dict.items():
        # 检查是否是敏感参数
        is_sensitive = any(sensitive in key.lower() for sensitive in sensitive_params)
        if is_sensitive:
            safe_dict[key] = '[REDACTED]'
        else:
            safe_dict[key] = value
    
    # 构建查询字符串
    from urllib.parse import urlencode
    return urlencode(safe_dict)


@app.route('/lastfm/', methods=['GET', 'POST'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_lastfm():
    lastfm_api_url = f"https://ws.audioscrobbler.com/2.0/?{request.query_string.decode('utf-8')}"

    if request.method == "POST":
        resp = requests.post(lastfm_api_url, json=None, headers=request.headers)
        app.logger.info(f"{resp.status_code} POST /lastfm/?{safe_query_string()}")
        return jsonify(resp.json()), resp.status_code

    method = request.args.get('method')
    if method.lower() == "artist.getinfo":
        artist_name = request.args.get('artist')
        
        # 并行查询网易云和Last.fm数据（9秒超时）
        (netease_data, lastfm_data, netease_success, lastfm_success, 
         elapsed_time, netease_error, lastfm_error) = parallel_query_artist_info(
            artist_name=artist_name,
            lastfm_api_url=lastfm_api_url,
            get_artist_profile_func=get_artist_profile,
            timeout=9  # 9秒超时，留1秒业务处理时间
        )
        
        app.logger.debug(f"artist.getinfo并行查询总耗时: {elapsed_time:.2f}秒")
        
        # 记录查询结果
        if netease_success:
            app.logger.debug(f"成功获取网易云数据: {artist_name}")
        elif netease_error:
            if netease_error == "Timeout":
                app.logger.warning(f"网易云API查询超时（9秒限制）: {artist_name}")
            else:
                app.logger.error(f"网易云API查询异常: {netease_error}")
                app.logger.error(traceback.format_exc())
        
        if lastfm_success:
            app.logger.debug(f"成功获取Last.fm数据: {artist_name}")
        elif lastfm_error:
            if lastfm_error == "Timeout":
                app.logger.warning(f"Last.fm查询超时（9秒限制）: {artist_name}")
            else:
                app.logger.error(f"Last.fm查询异常: {lastfm_error}")
        
        # 根据获取的数据情况决定返回什么（保留原方案的数据合并逻辑）
        if lastfm_success:
            # 有Last.fm数据，以其为模板
            result = lastfm_data
            
            # 如果有网易云数据，用网易云数据补充（网易云数据优先）
            if netease_success:
                # 替换image标签为网易云数据
                artist_result = result['artist']
                
                # 获取网易云图片URL
                netease_img1v1 = netease_data.get('img1v1Url', '')
                netease_pic = netease_data.get('picUrl', '')
                
                # 更新image数组
                if 'image' in artist_result:
                    for img in artist_result['image']:
                        size = img.get('size', '')
                        if size in ['small', 'medium']:
                            img['#text'] = netease_img1v1
                        elif size in ['large', 'extralarge', 'mega', '']:
                            img['#text'] = netease_pic
                
                # 更新bio summary
                if 'bio' in artist_result:
                    netease_brief = netease_data.get('briefDesc', '')
                    if netease_brief:
                        artist_result['bio']['summary'] = netease_brief
                        artist_result['bio']['content'] = netease_brief
                
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅Last.fm)")
            
            return jsonify(result)
        
        elif netease_success:
            # 只有网易云数据，构建Last.fm格式的响应
            # 以标准Last.fm结构为模板，填充网易云数据
            netease_img1v1 = netease_data.get('img1v1Url', '')
            netease_pic = netease_data.get('picUrl', '')
            netease_brief = netease_data.get('briefDesc', '')
            
            # 构建标准Last.fm结构
            lastfm_resp = {
                "artist": {
                    "name": artist_name,
                    "mbid": "",  # 网易云没有mbid
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}",
                    "image": [
                        {"#text": netease_img1v1, "size": "small"},
                        {"#text": netease_img1v1, "size": "medium"},
                        {"#text": netease_pic, "size": "large"},
                        {"#text": netease_pic, "size": "extralarge"},
                        {"#text": netease_pic, "size": "mega"},
                        {"#text": netease_pic, "size": ""}
                    ],
                    "streamable": "0",
                    "ontour": "0",
                    "stats": {
                        "listeners": "0",
                        "playcount": "0"
                    },
                    "similar": {
                        "artist": []
                    },
                    "tags": {
                        "tag": []
                    },
                    "bio": {
                        "links": {
                            "link": {
                                "#text": "",
                                "rel": "original",
                                "href": f"https://last.fm/music/{artist_name.replace(' ', '+')}/+wiki"
                            }
                        },
                        "published": "01 Jan 1970, 00:00",
                        "summary": netease_brief,
                        "content": netease_brief
                    }
                }
            }
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()}")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name}"})
    elif method.lower() == "album.getinfo":
        # 从请求参数中获取专辑和艺术家信息
        artist_name = request.args.get('artist')
        album_name = request.args.get('album')
        mbid = request.args.get('mbid', "")
        
        # 并行查询网易云和Last.fm数据（9秒超时）
        (netease_data, lastfm_data, netease_success, lastfm_success, 
         elapsed_time, netease_error, lastfm_error) = parallel_query_album_info(
            artist_name=artist_name,
            album_name=album_name,
            lastfm_api_url=lastfm_api_url,
            get_album_info_func=get_album_info,
            timeout=9  # 9秒超时
        )
        
        app.logger.debug(f"album.getinfo并行查询总耗时: {elapsed_time:.2f}秒")
        
        # 记录查询结果
        if netease_success:
            app.logger.debug(f"成功获取网易云专辑数据: {artist_name} - {album_name}")
        elif netease_error:
            if netease_error == "Timeout":
                app.logger.warning(f"网易云API查询超时（9秒限制）: {artist_name} - {album_name}")
            else:
                app.logger.error(f"网易云API查询异常: {netease_error}")
                app.logger.error(traceback.format_exc())
        
        if lastfm_success:
            app.logger.debug(f"成功获取Last.fm专辑数据: {artist_name} - {album_name}")
        elif lastfm_error:
            if lastfm_error == "Timeout":
                app.logger.warning(f"Last.fm查询超时（9秒限制）: {artist_name} - {album_name}")
            else:
                app.logger.error(f"Last.fm查询异常: {lastfm_error}")
        
        # 根据获取的数据情况决定返回什么（保留原方案的数据合并逻辑）
        if lastfm_success:
            # 有Last.fm数据，以其为模板
            result = lastfm_data
            
            # 如果有网易云数据，用网易云数据补充（网易云数据优先）
            if netease_success:
                # 替换image标签为网易云数据
                album_result = result['album']
                
                # 获取网易云图片URL
                netease_blur_pic = netease_data.get('blurPicUrl', '')
                netease_pic = netease_data.get('picUrl', '')
                
                # 更新image数组
                if 'image' in album_result:
                    for img in album_result['image']:
                        size = img.get('size', '')
                        if size in ['small', 'medium']:
                            img['#text'] = netease_blur_pic
                        elif size in ['large', 'extralarge', 'mega', '']:
                            img['#text'] = netease_pic
                
                # 更新wiki summary
                if 'wiki' in album_result:
                    netease_desc = netease_data.get('description', '')
                    if netease_desc:
                        album_result['wiki']['summary'] = netease_desc
                        album_result['wiki']['content'] = netease_desc
                
                # 下载封面
                download_image_async(netease_pic, artist_name, album_name)
                
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅Last.fm)")
            
            return jsonify(result)
        
        elif netease_success:
            # 只有网易云数据，构建Last.fm格式的响应
            netease_blur_pic = netease_data.get('blurPicUrl', '')
            netease_pic = netease_data.get('picUrl', '')
            netease_desc = netease_data.get('description', '')
            
            # 构建标准Last.fm结构
            lastfm_resp = {
                "album": {
                    "name": album_name,
                    "artist": artist_name,
                    "mbid": mbid,
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}/{album_name.replace(' ', '+')}",
                    "image": [
                        {"#text": netease_blur_pic, "size": "small"},
                        {"#text": netease_blur_pic, "size": "medium"},
                        {"#text": netease_pic, "size": "large"},
                        {"#text": netease_pic, "size": "extralarge"},
                        {"#text": netease_pic, "size": "mega"},
                        {"#text": netease_pic, "size": ""}
                    ],
                    "listeners": "0",
                    "playcount": "0",
                    "tracks": {
                        "track": []
                    },
                    "tags": {
                        "tag": []
                    },
                    "wiki": {
                        "published": "01 Jan 1970, 00:00",
                        "summary": netease_desc,
                        "content": netease_desc
                    }
                }
            }
            
            # 下载封面
            download_image_async(netease_pic, artist_name, album_name)
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()}")
            abort(400, {"code": 400, "message": f"无法查询到专辑 {album_name} (艺术家: {artist_name})"})
    elif method.lower() == "artist.gettoptracks":
        # 获取艺术家热门歌曲
        artist_name = request.args.get('artist')
        limit = int(request.args.get('limit', 50))
        
        # 并行查询网易云和Last.fm数据（9秒超时）
        (netease_data, lastfm_data, netease_success, lastfm_success, 
         elapsed_time, netease_error, lastfm_error) = parallel_query_artist_toptracks(
            artist_name=artist_name,
            limit=limit,
            lastfm_api_url=lastfm_api_url,
            get_artist_top_songs_func=get_artist_top_songs,
            timeout=9  # 9秒超时
        )
        
        app.logger.debug(f"artist.gettoptracks并行查询总耗时: {elapsed_time:.2f}秒")
        
        # 记录查询结果
        if netease_success:
            app.logger.debug(f"成功获取网易云热门歌曲数据: {artist_name}")
        elif netease_error:
            if netease_error == "Timeout":
                app.logger.warning(f"网易云查询超时（9秒限制）: {artist_name}")
            else:
                app.logger.error(f"网易云API查询异常: {netease_error}")
                app.logger.error(traceback.format_exc())
        
        if lastfm_success:
            app.logger.debug(f"成功获取Last.fm热门歌曲数据: {artist_name}")
        elif lastfm_error:
            if lastfm_error == "Timeout":
                app.logger.warning(f"Last.fm查询超时（9秒限制）: {artist_name}")
            else:
                app.logger.error(f"Last.fm查询异常: {lastfm_error}")
        
        # 根据获取的数据情况决定返回什么（保留原方案的优先逻辑）
        # 1. 如果有网易云数据，以网易云数据填充Last.fm格式，抛弃Last.fm数据
        if netease_success:
            tracks = []
            for i, song in enumerate(netease_data[:limit]):
                track = {
                    "name": song.get('name', ''),
                    "duration": str(song.get('duration', 0)),
                    "playcount": str(song.get('playCount', 0)),
                    "listeners": str(song.get('listeners', 0)),
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}/_/{song.get('name', '').replace(' ', '+')}",
                    "artist": {
                        "name": artist_name,
                        "mbid": "",
                        "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}"
                    },
                    "image": [
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": "small"},
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": "medium"},
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": "large"},
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": "extralarge"},
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": "mega"},
                        {"#text": song.get('album', {}).get('picUrl', ''), "size": ""}
                    ],
                    "@attr": {
                        "rank": str(i + 1)
                    }
                }
                tracks.append(track)
            
            lastfm_resp = {
                "toptracks": {
                    "track": tracks,
                    "@attr": {
                        "artist": artist_name,
                        "page": "1",
                        "perPage": str(len(tracks)),
                        "totalPages": "1",
                        "total": str(len(tracks))
                    }
                }
            }
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云数据填充)")
            return jsonify(lastfm_resp)
        
        # 2. 如果网易云超时/无数据，但Last.fm有数据，使用Last.fm数据
        elif lastfm_success:
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云无数据，使用Last.fm)")
            return jsonify(lastfm_data)
        
        # 3. 两者都没有数据，返回400错误
        else:
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()} (无数据)")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
    elif method.lower() in ["track.getsimilar", "artist.getsimilar"]:
        # 对于相似歌曲和相似艺术家，直接重定向到Last.fm原生接口
        app.logger.info(f"302 GET /lastfm/?{safe_query_string()} (重定向到Last.fm)")
        return redirect(lastfm_api_url)
    else:
        # 对其他请求直接重定向到原接口
        app.logger.info(f"302 GET /lastfm/?{safe_query_string()}")
        return redirect(lastfm_api_url)
