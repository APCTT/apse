from backend.sources.korea_ntb import KoreaNTBSource
from backend.sources.wipo_patentscope import WIPOPatentscopeSource
from backend.sources.ip_australia import IPAustraliaSource
from backend.sources.csir_india import CSIRIndiaSource
from backend.sources.dost_tapi import DOSTTAPISource
from backend.sources.tech2biz import Tech2BizSource
from backend.sources.jst_japan import JSTJapanSource
from backend.sources.nrdc_india import NRDCIndiaSource
from backend.sources.apctt import APCTTSource
from backend.sources.iti_sri_lanka import ITISriLankaSource
from backend.config import settings

_ip_aus = IPAustraliaSource()
_csir = CSIRIndiaSource()
_dost = DOSTTAPISource()
_tech2biz = Tech2BizSource()
_jst = JSTJapanSource()
_nrdc = NRDCIndiaSource()
_apctt = APCTTSource()
_iti_sri_lanka = ITISriLankaSource()

SOURCES = [
    *([KoreaNTBSource()] if settings.KOREA_NTB_API_KEY else []),
    WIPOPatentscopeSource(),
    _ip_aus,
    _csir,
    _dost,
    _tech2biz,
    _jst,
    _nrdc,
    _iti_sri_lanka,
    _apctt,
]

SOURCE_MAP = {s.id: s for s in SOURCES}
