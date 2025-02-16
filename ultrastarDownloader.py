import os
import subprocess

import requests
from pytubefix import YouTube

# Links
#- https://usdb.animux.de - The biggest database of UltraStar songs (lyrics only)
#- https://ultrastar-es.org/ - Smaller database of songs, includes audio and video. You can download **UltraStar WorldParty** here.


def login_usdb(usr, pwd):
    url = "https://usdb.animux.de/index.php?link=login"
    session = requests.Session()

    data = {'user': usr,
            'pass': pwd,
            'login': "Login"}

    req = session.request("POST", url, data=data)
    if req.status_code!=200 or req.text.find("Login or Password invalid") > 0:
        return None
    return session

def get_files_from_dir(dst_dir):
    ret = []
    for path, subdirs, files in os.walk(dst_dir):
        ret.extend(files)
    return ret


def get_all_songs(dst_dir):
    ret = []
    for path, subdirs, files in os.walk(dst_dir):
        if len(subdirs)>0:
            for subdir in subdirs:
                files = get_files_from_dir(dst_dir+"/"+subdir)
                if len(files)==3:
                    endings = set([f[-3:].upper() for f in files])
                    if "mp3" not in endings:
                        print (f" {subdir} missing mp3")
                    if "mp4" not in endings:
                        print (f" {subdir} missing mp4")
                if len(files)>=3:
                    ret.append(subdir)
    return ret

def download_song_txt(session, songid):
    ret = None

    url = f"https://usdb.animux.de/index.php?link=gettxt&id={songid}"
    data = {"wd":"1"}

    req = session.request("POST", url, data=data)

    start_pos = req.text.find("<textarea ")
    if start_pos>0:
        start_pos = req.text.find(">", start_pos)
        if start_pos > 0:
            end_pos = req.text.find("</textarea>", start_pos)
            if end_pos > 0:
                ret = req.text[start_pos+1:end_pos]
                ret = ret.replace("\r\n", "\n")
    return ret

def get_song_metadata(song_txt):
    ret = {}
    order = []
    cur_pos = 0
    end_tags_pos = 0
    while cur_pos<len(song_txt):
        end_pos = song_txt.find("\n", cur_pos)
        if end_pos <0:
            end_pos = len(song_txt)
        line = song_txt[cur_pos:end_pos]
        cur_pos = end_pos + 1
        if line.startswith("#"):
            end_tags_pos = cur_pos
            param_idx = line.find(":")
            if param_idx>0:
                k = line[1:param_idx]
                v = line[param_idx+1:]
                assert k not in ret
                ret[k] = v
                order.append(k)
    return ret, order, end_tags_pos

def update_tags(song_txt, end_tags_pos, meta, meta_order):
    ret = ("\n".join([f"#{k}:{meta[k]}" for k in meta_order]) +
            "\n" +
           song_txt[end_tags_pos:])
    return ret

def get_video_meta(line):
    ret = {}
    elements = line.split(",")
    for element in elements:
        param_idx = element.find("=")
        if param_idx > 0:
            k = element[0:param_idx]
            v = element[param_idx + 1:]
            assert k not in ret
            ret[k] = v

    if len(ret)==0:
        ret = None
    return ret

def get_youtube_id(session, song):
    url = f"https://usdb.animux.de/index.php?link=detail&id={song}"
    req = session.get(url)
    search1 = "<iframe "
    search1_end = "</iframe>"
    search2 = ' src="'
    search3 = 'https://www.youtube.com/embed/'
    cur_pos = 0
    ret = None
    while ret==None and cur_pos>=0 and cur_pos<len(req.text):
        cur_pos = req.text.find(search1, cur_pos)
        if cur_pos>0:
            end_pos = req.text.find(search1_end, cur_pos)
            if end_pos>0:
                find_pos = req.text.find(search2, cur_pos)
                if find_pos>0 and find_pos<end_pos:
                    find_pos_end = req.text.find('">', find_pos)
                    if find_pos_end>0:
                        url = req.text[find_pos+len(search2):find_pos_end]
                        if url.startswith(search3):
                            ret = url[len(search3):]
            cur_pos = end_pos+len(search1_end)
    return ret

def download_songcover(session, song, full_path, cover_filename):
    url = f"https://usdb.animux.de/data/cover/{song}.jpg"
    req = session.get(url)
    assert req.status_code==200

    file_path = full_path + "/" + cover_filename
    with open(file_path, "wb") as file:
        file.write(req.content)

def run_ffmpg(output_path, input, output, params):
    ffmpeg = os.path.dirname(__file__)+"/"+"ffmpeg.exe"
    subprocess.run([ffmpeg, "-i", input, *params, output], cwd=output_path, check=True)

def download_video(youtube_link, path, filename):
    yt = YouTube(youtube_link, use_oauth=True)
    stream = yt.streams.filter(only_video=True).order_by('resolution').desc().first()
    tmp_filename = "youtube_audio.mp4"
    stream.download(output_path=path, filename=tmp_filename)
    run_ffmpg(path, tmp_filename, filename, ["-vcodec", "mpeg4"])
    os.remove(path+"/"+tmp_filename)

def download_audio(youtube_link, path, filename):
    yt = YouTube(youtube_link, use_oauth=True)
    stream = yt.streams.filter(only_audio=True, mime_type='audio/mp4').desc().first()
    tmp_filename = "youtube_audio.mp3"
    stream.download(output_path=path, filename=tmp_filename)
    run_ffmpg(path, tmp_filename, filename, ["-acodec", "mp3"])
    os.remove(path+"/"+tmp_filename)


def download_video_audio(youtube_id, dir_path, audio_filename, video_filename):
    youtube_link = f"https://www.youtube.com/watch?v={youtube_id}"
    if youtube_id is not None:
        assert video_filename is not None
        download_video(youtube_link, dir_path, video_filename)
    download_audio(youtube_link, dir_path, audio_filename)

def download_songs(dst_dir, songs, usr, pwd):
    ret = None
    all_songs = get_all_songs(dst_dir)
    session = login_usdb(usr, pwd)
    if session is None:
        print("Error login to usdb.animux.de.")
        return ret
    else:
        ret = []
        for song in songs:
            song_txt = download_song_txt(session, song)
            if song_txt is None:
                print(f"Error, song {song} not found!")
            else:
                meta, meta_order, end_tags_pos = get_song_metadata(song_txt)
                dirname = meta["ARTIST"] + " - " + meta["TITLE"]

                youtube_id = None
                if 'MP3' not in meta:
                    meta['MP3'] = dirname = ".mp3"
                if 'COVER' not in meta:
                    meta['COVER'] = dirname + ".jpg"

                assert meta["MP3"].endswith(".mp3")
                if "VIDEO" in meta and meta["VIDEO"].find("=") > 0:
                    video_meta = get_video_meta(meta["VIDEO"])
                    if 'v' in video_meta:
                        youtube_id = video_meta['v']
                    elif 'V' in video_meta:
                        youtube_id = video_meta['V']
                if youtube_id is not None or "VIDEO" not in meta or (not meta["VIDEO"].endswith(".mp4")):
                    meta["VIDEO"] = meta["MP3"][:-4] + '.mp4'

                song_txt = update_tags(song_txt, end_tags_pos, meta, meta_order)

                ret.append(get_songdata_from_txt(song, song_txt))

                if dirname in all_songs:
                    print(f"  {dirname} allready exists. skipping")
                else:
                    print(f"  {dirname} downloading")
                    full_path = dst_dir + "/" + dirname
                    if not os.path.exists(full_path):
                        os.mkdir(full_path)

                    with open(full_path+"/"+dirname+".txt", "w", encoding="utf-8") as file:
                        file.write(song_txt)

                    download_songcover(session, song, full_path, meta["COVER"])
                    if youtube_id is None:
                        youtube_id = get_youtube_id(session, song)
                        if "VIDEO" not in meta:
                            meta["VIDEO"] = meta["MP3"][:-4] + '.mp4'
                    else:
                        youtube_id2 = get_youtube_id(session, song)
                        if youtube_id!=youtube_id2:
                            print(f"Warning, differen you tube ids found {youtube_id} {youtube_id2}")

                    assert youtube_id is not None
                    video = meta["VIDEO"] if "VIDEO" in meta else None
                    download_video_audio(youtube_id, full_path, meta["MP3"], video)
    return ret

def download_all_songs(dst_dir, all_songs, usr, pwd):
    song_list = []
    for categorie, songs in all_songs:
        print(categorie)
        full_path = dst_dir+"/"+categorie
        if not os.path.exists(full_path):
            os.mkdir(full_path)

        songs = download_songs(full_path, songs, usr, pwd)
        if songs is not None:
            song_list.extend(songs)
    return song_list

def get_songsdata_from_html(content):
    ret = []
    cur_pos = 0
    search1 = '<td onclick="show_detail('
    old_line_header = ""
    columns = []
    while cur_pos < len(content):
        td_beg = content.find(search1, cur_pos)
        if td_beg>0:
            td_beg_end = content.find(')"', td_beg)
            cur_line_header = content[td_beg+13:td_beg_end+1]
            if cur_line_header != old_line_header:
                if len(columns)>0:
                    search2 = '<a href="?link=detail&id='
                    assert columns[2].startswith(search2)
                    search_end = columns[2].find('">', len(search2))
                    assert search_end>0
                    id = int(columns[2][len(search2):search_end])
                    title = columns[2][search_end+2:]
                    artist = columns[1]
                    genre = columns[3]
                    year = columns[4]
                    edition = columns[5]
                    golden_notes = columns[6]
                    ret.append((id, title, artist, genre, year, edition, golden_notes))
                    columns = []
                old_line_header = cur_line_header
            line_content_start = content.find(">", td_beg_end)
            line_content_end = content.find("</td>", line_content_start)
            cur_line_content = content[line_content_start+1:line_content_end]
            columns.append(cur_line_content)
            cur_pos = line_content_end + 4
        else:
            cur_pos = len(content)
    return ret

def get_songdata_from_txt(id, song_txt):
    meta, meta_order, end_tags_pos = get_song_metadata(song_txt)
    title = meta.get("TITLE", "")
    artist = meta.get("ARTIST", "")
    genre = meta.get("GENRE", "")
    year = meta.get("YEAR", "")
    edition = meta.get("EDITION", "")
    golden_notes = False
    return (id, title, artist, genre, year, edition, golden_notes)


def get_songs_list(usr, pwd):
    session = login_usdb(usr, pwd)
    if session is None:
        print("Error login to usdb.animux.de.")
        return None
    elements_per_page = 30
    data = {
        "interpret": "",
        "title": "",
        "edition": "",
        "language": "",
        "genre": "",
        "year": "",
        "creator": "",
        "order": "id",
        "ud": "asc",
        "limit": str(elements_per_page),
        "details": "1"
    }
    url = "https://usdb.animux.de/?link=list"
    req = session.request("POST", url, data=data)
    ret = []
    cur_page = 0
    num_pages = 1
    while cur_page<num_pages:
        if req.status_code==200:
            search = "<br>There are  "
            search2 = '  results on  '
            search3 = ' page(s)<br>'
            result_pos = req.text.find(search)
            pages_pos = req.text.find(search2, result_pos)
            pages_pos_end = req.text.find(search3, pages_pos)
            num_pages = int(req.text[pages_pos+len(search2):pages_pos_end])
            songs = get_songsdata_from_html(req.text)
            ret.extend(songs)
        cur_page += 1
        if cur_page<num_pages:
            print(f"reading page {cur_page}/{num_pages}")
            data["start"] = str(cur_page * elements_per_page)
            req = session.request("POST", url, data=data)

    return ret

def get_all_playlists(song_list):
    ret = set()
    for song_data in song_list:
        edition = song_data[5]
        if len(edition)>0:
            editions = edition.split(", ")
            for edition in editions:
                if edition not in ret:
                    ret.add(edition)
    return ret

def get_songs_from_playlist(song_list, playlist_name):
    ret = set()
    for song_data in song_list:
        edition = song_data[5]
        if len(edition)>0 and edition == playlist_name:
            ret.add(song_data[0])
    return ret

def read_playlist(playlist_dir, playlist_name):
    pass

def write_playlist(playlist_dir, playlist_name, songs, song_list):
    id_map = dict([(s[0], e) for e,s in enumerate(song_list)])
    with open(playlist_dir + "/" + playlist_name + ".ups", "w") as file:
        file.write(f"#Name: {playlist_name}\n")
        file.write(f"#Songs:\n")
        for song in songs:
            if song not in id_map:
                print("no")
            assert song in id_map
            song_data = song_list[id_map[song]]
            file.write(f"{song_data[2]} : {song_data[1]}\n")

def get_playlists(playlist_dir, song_list):
    files = get_files_from_dir(playlist_dir)
    for file in files:
        assert file.endswith(".ups")
        content = read_playlist(playlist_dir, file)

def generate_playlists(playlist_dir, all_songs, song_list):
    for categorie, songs in all_songs:
        write_playlist(playlist_dir, categorie, songs, song_list)

def main():
    usr = "cpecinovsky"
    pwd = "DasPasswortIstGeheim"
    dst_dir = "D:/Games/UltraStar Songs"
    playlist_dir = "D:/Games/UltraStar Playlists"

    song_list = []
    #song_list = get_songs_list(usr, pwd)
    ####playlists = get_all_playlists(song_list)
    #playlists = list(playlists)
    #playlists.sort()
    #print(playlists)

    ronja_songs = ("Ronja",
                        [29715, #thats so true
                         20996, #believer
                         25203, #abc
                         29626, #APT
                         28946, #lose control
                         3482, #blue
                         26214, #beggin
                         29938, #belong together
                         28769, #texas holdem
                         17519, #dirty dancing
                         9791, #waka waka # does not exist anymore
                         2228, #wahnsinn
                         24847, #expresso
                         22157, #cordola
                         19671, #bankueberfall
                         3307, #dirty
                         21222, #johnny depp
                         13095, #sexy and i know it
                         5725, #arsch
                         11408, #adele
                         22713, #dance monkey
                         1298, #völlig losgeläst
                         3860, #take on me
                         29184, #I Don’t Wanna Wait
                         21082, #Dragostea din tei
                  ])

    clemens_songs = ("Clemens",
                     [4738,  #in the end
                      18601,  # temple of love
                      1926,  # last resort
                      305,  # Tribute
                      1171,  # verdammt
                      19534,  # sounds of silence
                      4322,  # run to the hills
                      24689,  # wir zwei
                      18439,  #my way
                      3440,  #titanik
                      2727,  # codo
                      ])

    aerzte_songs = ("Die Ärzte", [
                266, #ohne dich
                278, #teenager liebe
        394, #der graf
        2317, #deine schuld
        2299, #zu spät
        3455, #nur einen kuss
        3907, #junge
        4752, #manchmal
        4756, #augen zu
        8175, #uhrockbar
                    ])

    volbeat_songs = ("Volbeat", [
        22280,  #For evigt
    ])

    rammstein_songs = ("Rammstein", [
        1388,  #seemann
        1400, #engel
        1599, #du hast
        3747, #ohne dich
        16429, #sonne
    ])

    badreligion_songs = ("Bad Religion", [
        149,  #jesus
        5579, #punkrocksong
        23855, #skzscaraper
        29398, #sorrow
    ])

    disney_songs = ("Disney", [
                        18719, #eiskoenigin
                        5334,  # probiers mal mit ...
                        ])

    metallica_songs = ("Metallica",
                       [
                           3669, #whiskey in the jar
                           4118, #nothing else matters
                           5076, #sad but true
                       ])

    lady_gaga_songs = ("Lady Gaga",
                       [
                           11052, #bad romance
                           23775, #shallow
                       ])
    sing_star_queen = ("SingStar Queen",
                       [
                           6052, #we will rock you
                       ])

    all_songs = [ronja_songs,
                 clemens_songs,
                 disney_songs,
                 metallica_songs,
                 aerzte_songs,
                 volbeat_songs,
                 rammstein_songs,
                 badreligion_songs,
                 lady_gaga_songs,
                 sing_star_queen]

    downloaded_songs = download_all_songs(dst_dir, all_songs, usr, pwd)
    num_songs = len([x for song in all_songs for x in song[1]])
    assert len(downloaded_songs) == num_songs

    song_list.extend(downloaded_songs)
    generate_playlists(playlist_dir, all_songs, song_list)

    return 0


if __name__ == "__main__":
    retval = main()

    print("exited with return code %s" % retval)
    exit(retval)
