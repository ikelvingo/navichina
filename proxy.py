import re
import requests
import traceback
from flask_caching import Cache
from functools import cache
from urllib.parse import unquote
from flask import Flask, abort, request, jsonify, redirect
from cover import download_image_async
from search import get_album_info, get_artist_profile, get_artist_top_songs, get_similar_songs  # type: ignore

app = Flask(__name__)


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


@app.route('/lastfm/', methods=['GET', 'POST'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_lastfm():
    lastfm_api_url = f"https://ws.audioscrobbler.com/2.0/?{request.query_string.decode('utf-8')}"

    if request.method == "POST":
        resp = requests.post(lastfm_api_url, json=None, headers=request.headers)
        app.logger.info(f"{resp.status_code} POST /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
        return jsonify(resp.json()), resp.status_code

    method = request.args.get('method')
    if method.lower() == "artist.getinfo":
        artist_name = request.args.get('artist')
        
        # 同时获取网易云数据和Last.fm数据
        netease_data = None
        lastfm_data = None
        netease_error = None
        lastfm_error = None
        
        # 1. 尝试获取网易云数据
        try:
            artist_name_1 = None
            if any(substring in artist_name for substring in [' and ', "&"]):
                sp = re.split(r" and |&", artist_name)
                artist_name_1 = sp[0]
            
            artist_profile = get_artist_profile(artist_name)
            if not artist_profile and artist_name_1 is not None:
                artist_profile = get_artist_profile(artist_name_1)
            
            if artist_profile:
                netease_data = artist_profile['artist']
                app.logger.debug(f"成功获取网易云数据: {artist_name}")
            else:
                app.logger.debug(f"网易云没有找到艺术家: {artist_name}")
        except Exception as e:
            netease_error = e
            app.logger.error(f"网易云API查询异常: {e}")
            app.logger.error(traceback.format_exc())
        
        # 2. 尝试获取Last.fm数据
        try:
            lastfm_response = requests.get(lastfm_api_url, headers=request.headers, timeout=5)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    app.logger.debug(f"成功获取Last.fm数据: {artist_name}")
                else:
                    app.logger.debug(f"Last.fm返回错误: {lastfm_data.get('error')}")
                    lastfm_data = None
            else:
                app.logger.debug(f"Last.fm HTTP错误: {lastfm_response.status_code}")
        except requests.exceptions.Timeout:
            lastfm_error = "Timeout"
            app.logger.warning(f"Last.fm查询超时: {artist_name}")
        except Exception as e:
            lastfm_error = e
            app.logger.error(f"Last.fm查询异常: {e}")
        
        # 3. 根据获取的数据情况决定返回什么
        if lastfm_data:
            # 有Last.fm数据，以其为模板
            result = lastfm_data
            
            # 如果有网易云数据，用网易云数据补充
            if netease_data:
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
                
                app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (仅Last.fm)")
            
            return jsonify(result)
        
        elif netease_data:
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
            
            app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name}"})
    elif method.lower() == "album.getinfo":
        # 从请求参数中获取专辑和艺术家信息
        artist_name = request.args.get('artist')
        album_name = request.args.get('album')
        mbid = request.args.get('mbid', "")
        
        # 同时获取网易云数据和Last.fm数据
        netease_data = None
        lastfm_data = None
        netease_error = None
        lastfm_error = None
        
        # 1. 尝试获取网易云数据
        try:
            album_info = get_album_info(artist_name, album_name)
            if album_info:
                netease_data = album_info
                app.logger.debug(f"成功获取网易云专辑数据: {artist_name} - {album_name}")
            else:
                app.logger.debug(f"网易云没有找到专辑: {artist_name} - {album_name}")
        except Exception as e:
            netease_error = e
            app.logger.error(f"网易云API查询异常: {e}")
            app.logger.error(traceback.format_exc())
        
        # 2. 尝试获取Last.fm数据
        try:
            lastfm_response = requests.get(lastfm_api_url, headers=request.headers, timeout=5)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    app.logger.debug(f"成功获取Last.fm专辑数据: {artist_name} - {album_name}")
                else:
                    app.logger.debug(f"Last.fm返回错误: {lastfm_data.get('error')}")
                    lastfm_data = None
            else:
                app.logger.debug(f"Last.fm HTTP错误: {lastfm_response.status_code}")
        except requests.exceptions.Timeout:
            lastfm_error = "Timeout"
            app.logger.warning(f"Last.fm查询超时: {artist_name} - {album_name}")
        except Exception as e:
            lastfm_error = e
            app.logger.error(f"Last.fm查询异常: {e}")
        
        # 3. 根据获取的数据情况决定返回什么
        if lastfm_data:
            # 有Last.fm数据，以其为模板
            result = lastfm_data
            
            # 如果有网易云数据，用网易云数据补充
            if netease_data:
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
                
                app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (仅Last.fm)")
            
            return jsonify(result)
        
        elif netease_data:
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
            
            app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
            abort(400, {"code": 400, "message": f"无法查询到专辑 {album_name} (艺术家: {artist_name})"})
    elif method.lower() == "artist.gettoptracks":
        # 获取艺术家热门歌曲
        artist_name = request.args.get('artist')
        limit = int(request.args.get('limit', 50))
        
        # 1. 优先尝试获取网易云数据
        netease_data = None
        netease_timeout = False
        
        try:
            top_songs = get_artist_top_songs(artist_name, limit)
            if top_songs:
                netease_data = top_songs
                app.logger.debug(f"成功获取网易云热门歌曲数据: {artist_name}")
            else:
                app.logger.debug(f"网易云没有找到热门歌曲: {artist_name}")
        except requests.exceptions.Timeout:
            netease_timeout = True
            app.logger.warning(f"网易云查询超时: {artist_name}")
        except Exception as e:
            app.logger.error(f"网易云API查询异常: {e}")
            app.logger.error(traceback.format_exc())
        
        # 2. 如果有网易云数据，以网易云数据填充Last.fm格式，抛弃Last.fm数据
        if netease_data:
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
            
            app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云数据填充)")
            return jsonify(lastfm_resp)
        
        # 3. 如果网易云超时（没有数据但有超时错误），尝试使用Last.fm数据
        elif netease_timeout:
            try:
                lastfm_response = requests.get(lastfm_api_url, headers=request.headers, timeout=5)
                if lastfm_response.status_code == 200:
                    lastfm_data = lastfm_response.json()
                    if 'error' not in lastfm_data:
                        app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云超时，使用Last.fm)")
                        return jsonify(lastfm_data)
                    else:
                        app.logger.debug(f"Last.fm返回错误: {lastfm_data.get('error')}")
                else:
                    app.logger.debug(f"Last.fm HTTP错误: {lastfm_response.status_code}")
            except requests.exceptions.Timeout:
                app.logger.warning(f"Last.fm查询超时: {artist_name}")
                # Last.fm也超时，返回400错误
                app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云和Last.fm都超时)")
                abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
            except Exception as e:
                app.logger.error(f"Last.fm查询异常: {e}")
                # Last.fm异常，返回400错误
                app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (Last.fm异常)")
                abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
        
        # 4. 如果网易云没有数据也没有超时（即查询失败），尝试使用Last.fm数据
        else:
            try:
                lastfm_response = requests.get(lastfm_api_url, headers=request.headers, timeout=5)
                if lastfm_response.status_code == 200:
                    lastfm_data = lastfm_response.json()
                    if 'error' not in lastfm_data:
                        app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (网易云无数据，使用Last.fm)")
                        return jsonify(lastfm_data)
                    else:
                        app.logger.debug(f"Last.fm返回错误: {lastfm_data.get('error')}")
                else:
                    app.logger.debug(f"Last.fm HTTP错误: {lastfm_response.status_code}")
            except requests.exceptions.Timeout:
                app.logger.warning(f"Last.fm查询超时: {artist_name}")
                # Last.fm超时，返回400错误
                app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (Last.fm超时)")
                abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
            except Exception as e:
                app.logger.error(f"Last.fm查询异常: {e}")
                # Last.fm异常，返回400错误
                app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (Last.fm异常)")
                abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
            
            # 如果Last.fm也没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (无数据)")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
    elif method.lower() in ["track.getsimilar", "artist.getsimilar"]:
        # 对于相似歌曲和相似艺术家，直接重定向到Last.fm原生接口
        app.logger.info(f"302 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))} (重定向到Last.fm)")
        return redirect(lastfm_api_url)
    else:
        # 对其他请求直接重定向到原接口
        app.logger.info(f"302 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
        return redirect(lastfm_api_url)
