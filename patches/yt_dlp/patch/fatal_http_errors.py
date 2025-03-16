from yt_dlp.extractor.youtube import YoutubeIE


class PatchedYoutubeIE(YoutubeIE):

    def FUNC(self):
        pass


#YoutubeIE.__unpatched__FUNC = YoutubeIE.FUNC
#YoutubeIE.FUNC = PatchedYoutubeIE.FUNC
