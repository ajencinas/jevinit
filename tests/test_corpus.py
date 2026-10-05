from zeroops.corpus import generate_corpus
from zeroops.schema import REMEDIATION_ACTIONS


def test_corpus_deterministic_and_sized():
    a = generate_corpus(n_variants=4)
    b = generate_corpus(n_variants=4)
    assert len(a) == len(b) == 56
    assert [i.id for i in a] == [i.id for i in b]
    assert [i.state for i in a] == [i.state for i in b]


def test_ground_truth_is_valid():
    for inc in generate_corpus(n_variants=2):
        gt = inc.ground_truth
        assert isinstance(gt["real_incident"], bool)
        assert isinstance(gt["auto_safe"], bool)
        assert gt["correct_action"] in REMEDIATION_ACTIONS
        assert isinstance(gt["severity"], int) and 0 <= gt["severity"] <= 3
        assert gt["failure_category"] and gt["root_cause"]
        assert inc.state.strip()


def test_has_flukes_and_incidents():
    corpus = generate_corpus(n_variants=1)
    reals = [i for i in corpus if i.ground_truth["real_incident"]]
    flukes = [i for i in corpus if not i.ground_truth["real_incident"]]
    assert reals and flukes
    assert any(i.ground_truth["auto_safe"] for i in corpus)
    assert any(not i.ground_truth["auto_safe"] for i in corpus)


def test_no_service_depends_on_itself_and_suspects_are_real_components():
    from zeroops.schema import SERVICES
    for inc in generate_corpus(n_variants=4):
        assert inc.meta["service"] != inc.meta["dependency"], inc.id
        assert inc.ground_truth["suspect_component"] in SERVICES, inc.id


def test_dependency_side_faults_blame_the_dependency():
    for inc in generate_corpus(n_variants=4):
        if inc.archetype in ("dependency_outage", "network_partition", "db_saturation", "data_corruption"):
            assert inc.ground_truth["suspect_component"] == inc.meta["dependency"], inc.id
        if inc.archetype in ("db_saturation", "data_corruption"):
            assert inc.meta["dependency"] == "db-primary", inc.id


def test_bad_deploy_log_names_code_in_the_alerting_service():
    from zeroops.corpus import _HANDLERS
    for inc in generate_corpus(n_variants=4):
        if inc.archetype == "bad_deploy":
            assert _HANDLERS[inc.meta["service"]] in inc.state


def test_fingerprint_is_stable_and_label_sensitive():
    from zeroops.corpus import corpus_fingerprint
    a, b = generate_corpus(4), generate_corpus(4)
    assert corpus_fingerprint(a) == corpus_fingerprint(b)
    b[0].ground_truth["severity"] = 0
    assert corpus_fingerprint(a) != corpus_fingerprint(b)
