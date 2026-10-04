"""
Router tests for Step 30B adapters (Cult of Pedagogy, Spencer Education, Wonkhe).
"""
import pytest
from src.collectors.router import SourceRouter


def test_source_router_step30b_domains():
    router = SourceRouter()

    # 1. Cult of Pedagogy
    res, adapter = router.route("https://www.cultofpedagogy.com/chatgpt-example-machine/")
    assert res.supported is True
    assert res.adapter_name == "CultOfPedagogyAdapter"
    assert res.platform_name == "Cult of Pedagogy"
    assert adapter.__class__.__name__ == "CultOfPedagogyAdapter"

    # 2. Spencer Education
    res, adapter = router.route("https://spencereducation.com/creative-constraints/")
    assert res.supported is True
    assert res.adapter_name == "SpencerEducationAdapter"
    assert res.platform_name == "Spencer Education"
    assert adapter.__class__.__name__ == "SpencerEducationAdapter"

    # 3. Wonkhe
    res, adapter = router.route("https://wonkhe.com/blogs/chatgpt-assessment-and-cheating-have-we-tried-trusting-students/")
    assert res.supported is True
    assert res.adapter_name == "WonkheAdapter"
    assert res.platform_name == "Wonkhe"
    assert adapter.__class__.__name__ == "WonkheAdapter"
