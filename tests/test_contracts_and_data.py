import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from subsurface_agent.contracts import Interval, SliceRef
from subsurface_agent.data import FEATURES, SPLITS, TARGETS, valid_label_mask
from subsurface_agent.tools import canonical_curve, select_interval


def test_reversed_and_nonfinite_depths_rejected():
    for bounds in [(10, 2), (1, float("inf")), (float("nan"), 4)]:
        with pytest.raises(ValidationError):
            Interval(well=3, start=bounds[0], end=bounds[1])


def test_path_injection_and_unknown_arguments_rejected():
    with pytest.raises(ValidationError):
        SliceRef(slice_id="../../.env")
    with pytest.raises(ValidationError):
        Interval(well=3, start=1, end=2, unit="ft", output_path=".env")


def test_known_aliases_are_semantic_not_just_valid_strings():
    assert canonical_curve("gamma ray") == "GR"
    assert canonical_curve("RHOB") == "DEN"
    with pytest.raises(ValueError, match="Unsupported input curve"):
        canonical_curve("MAGIC_LOG")


def test_ft_metamorphic_unit_conversion_keeps_boundary_rows():
    frame = pd.DataFrame({"WELLNUM": [3] * 3, "DEPTH": [10600., 10800., 11000.]})
    a = select_interval(frame, Interval(well=3, start=10600, end=11000, unit="ft"))
    b = select_interval(frame, Interval(well=3, start=3230.88, end=3352.8, unit="m"))
    pd.testing.assert_frame_equal(a, b)


def test_label_quality_excludes_out_of_bounds_without_clipping():
    frame = pd.DataFrame({feature: [1., 1., 1.] for feature in FEATURES})
    frame["PHIF"], frame["SW"], frame["VSH"] = [.2, .2, np.nan], [.5] * 3, [.1, 1.3, .1]
    assert valid_label_mask(frame).tolist() == [True, False, False]
    assert frame.loc[1, "VSH"] == 1.3


def test_all_prespecified_wells_are_disjoint():
    assert set(SPLITS["train"]).isdisjoint(SPLITS["validation"])
    assert set(SPLITS["train"]).isdisjoint(SPLITS["test"])
    assert set(SPLITS["validation"]).isdisjoint(SPLITS["test"])
    assert sorted(sum(SPLITS.values(), [])) == list(range(9))
