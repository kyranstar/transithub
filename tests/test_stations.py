from transithub.mta.stations import load_stations, search_stations


def test_dekalb_l_train():
    matches = [s for s in search_stations("dekalb") if "L" in s.routes]
    assert any(s.gtfs_stop_id == "L16" and s.north_label == "Manhattan" for s in matches)


def test_myrtle_wyckoff_m_train():
    matches = search_stations("myrtle-wyckoff")
    assert any(s.gtfs_stop_id == "M08" and "M" in s.routes for s in matches)
    assert any(s.gtfs_stop_id == "L17" and "L" in s.routes for s in matches)


def test_load_stations_nonempty():
    assert len(load_stations()) > 400
