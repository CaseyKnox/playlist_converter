import requests
from time import sleep

class PlaylistConverter:

    def __init__(self, token):
        self.token = token

    @staticmethod
    def search(song='', artist='', album='', token='', search_type='track'):
        baseURL = "https://api.spotify.com/v1/search"

        # convert space to %20
        song = song.replace(" ", "%20")
        artist = artist.replace(" ", "%20")
        album = album.replace(" ", "%20")

        query = 'q='
        if song != '':
            query += f"{song}"
        if artist != '':
            query += f"%20artist:{artist}"
        if album != '':
            query += f"%20album:{album}"
        
        query += f"&type={search_type}"

        response = requests.get(url=f"{baseURL}?{query}", headers={"Content-Type":"application/json", 
                        "Authorization":f"Bearer {token}"})

        j = response.json()

        if int(response.status_code) == 429: # too many requests
            # we must wait
            print(f"Rate limiting! Sleeping for {j['Retry-After']}")
            sleep(int(j['Retry-After']) + 1)
            response = requests.get(url=f"{baseURL}?{query}", headers={"Content-Type":"application/json", 
                            "Authorization":f"Bearer {token}"})
        elif int(response.status_code) != 200:
            print(f"Error code: {response.status_code}")
            raise Exception(response.status_code)

        return j
    
    @staticmethod
    def matchTrackSearch(search_response, song_apple='', artists_apple=[], album_apple='', auto_match=True, token=''):
        '''
        Take a bunch of tracks from a spotify query and try to match it 
        '''
        uri = None
        for item in search_response['tracks']['items']:
            song_spotify = item['name']
            artists_spotify = [artist['name'] for artist in item['artists']]
            album_spotify = item['album']['name']

            # print(f"Item: {song_spotify} by {artists_spotify} on album_spotify")
            if auto_match:
                # auto match if no conditionals are given
                match = True 

            # create conditional
            if song_apple != '':
                match = song_spotify == song_apple
            if artists_apple != '':
                # check that every apple artist is in the spotify artists
                for artist_a in artists_apple:
                    match = match and artist_a in artists_spotify
            if album_apple != '':
                match = match and album_spotify == album_apple
            
            if match:
                msg = "Matched Found!\n"
                if song_apple != '':
                    msg += f"\t{song_spotify} == {song_apple}\n"
                if artists_apple != '':
                    msg += f"\t{artists_spotify} == {artists_apple}\n"
                if album_apple != '':
                    msg += f"\t{album_spotify} == {album_apple}\n"

                print(msg)
                uri = item['uri']
                break

        return uri

    def matchingLogic(self, entry):
        '''
        1. Search by song and artist
        2. Try to match song and multiple artists 
        3. try to match song with one artist

        1. search by song and first artist first name
        2. Try to match song and artist first name
        3. try to match song with one artist
        '''
        # clean song name, artists, etc 
        entry = self.cleanEntry(entry)

        # first search by song and artist
        for artist in entry['artists']:
            resp = self.search(song=entry['song'], artist=artist, token=self.token)
            if len(resp['tracks']['items']) > 0:
                uri = self.matchTrackSearch(resp, song_apple=entry['song'], artists_apple=entry['artist'], auto_match=False, token=self.token)

                if uri == None:
                    # match first artist
                    uri = self.matchTrackSearch(resp, song_apple=entry['song'], artists_apple=[entry['artist'][0]], auto_match=False, token=self.token)


        resp = self.search(song=entry['song'], token=self.token)
        pass 

    def cleanEntry(self, entry):
        pass