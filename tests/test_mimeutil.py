from fpv.mimeutil import ext_from_filename, ext_from_mime, is_video_mime
from fpv.google import build_download_url


def test_mime_and_download_url():
    assert ext_from_filename("photo.JPG") == "jpg"
    assert ext_from_mime("image/png") == "png"
    assert is_video_mime("video/mp4") is True
    assert build_download_url("http://example", "image/jpeg") == "http://example=d"
    assert build_download_url("http://example", "video/mp4") == "http://example=dv"
