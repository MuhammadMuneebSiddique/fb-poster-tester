from tiktok_downloader import snaptik, ssstik, tikwm, Tikmate

url = "https://www.tiktok.com/@malaysia__22/video/7047692246874885402"

# # Method 1: Snaptik
# d = snaptik(url)
# d[0].download("video.mp4")

# # Method 2: SSSTik
# d = ssstik(url)
# print(d)
# # d[0].download("video.mp4")

# Method 3: TikWM
d = tikwm(url)
d[0].download("video.mp4")