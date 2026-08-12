from backend.sources.korea_ntb import KoreaNTBSource
from backend.sources.wipo_patentscope import WIPOPatentscopeSource
from backend.sources.csir_india import CSIRIndiaSource
from backend.sources.dost_tapi import DOSTTAPISource
from backend.sources.tech2biz import Tech2BizSource
from backend.sources.jst_japan import JSTJapanSource
from backend.sources.nrdc_india import NRDCIndiaSource
from backend.sources.apctt import APCTTSource
from backend.sources.iti_sri_lanka import ITISriLankaSource
from backend.sources.malaysia_rd_portal import MalaysiaRDPortalSource
from backend.config import settings

_csir = CSIRIndiaSource()
_dost = DOSTTAPISource()
_tech2biz = Tech2BizSource()
_jst = JSTJapanSource()
_nrdc = NRDCIndiaSource()
_apctt = APCTTSource()
_iti_sri_lanka = ITISriLankaSource()
_malaysia_rd_portal = MalaysiaRDPortalSource()

SOURCES = [
    *([KoreaNTBSource()] if settings.KOREA_NTB_API_KEY else []),
    WIPOPatentscopeSource(),
    _csir,
    _dost,
    _tech2biz,
    _jst,
    _nrdc,
    _iti_sri_lanka,
    _malaysia_rd_portal,
    _apctt,
]

SOURCE_MAP = {s.id: s for s in SOURCES}
