"""art_source: free, public-domain museum art (CC0 open-access collections).

Each tool searches one museum's open API and downloads only objects the museum itself flags
as public domain / CC0. Anything not flagged is refused, never downloaded. Every download is
recorded in ``projects/<id>/assets/PROVENANCE.json`` (lib/provenance.py).
"""
