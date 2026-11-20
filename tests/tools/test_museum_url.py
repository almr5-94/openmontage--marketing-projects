from tools.art_source.museum_art import _safe_url


def test_spaces_in_a_museum_file_name_are_encoded_once():
    u = "https://images.metmuseum.org/CRDImages/is/web-large/Farman - mma 1998 color 1.JPG"
    assert _safe_url(u) == "https://images.metmuseum.org/CRDImages/is/web-large/Farman%20-%20mma%201998%20color%201.JPG"
    assert _safe_url(_safe_url(u)) == _safe_url(u)
    q = "https://api.example.org/search?q=pen%20box&limit=5"
    assert _safe_url(q) == q
