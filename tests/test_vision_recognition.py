from app.models import Bridge
from app.services.vision_recognition import build_bridge_catalog


def test_catalog_csv_format(db_session):
    db_session.add(Bridge(name="赵州桥", region="河北", era="隋唐", bridge_type="石拱桥"))
    db_session.add(Bridge(name="南京长江大桥", region="江苏", era="现代", bridge_type="公铁两用桁架桥"))
    db_session.flush()

    csv = build_bridge_catalog(db_session)

    assert csv.splitlines()[0] == "name,region,era,bridge_type"
    assert "赵州桥,河北,隋唐,石拱桥" in csv
    assert "南京长江大桥,江苏,现代,公铁两用桁架桥" in csv


def test_catalog_handles_null_columns(db_session):
    db_session.add(Bridge(name="X 桥", region=None, era=None, bridge_type=None))
    db_session.flush()
    csv = build_bridge_catalog(db_session)
    assert "X 桥,,," in csv
