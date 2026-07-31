from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "instrumentacao_image_manager.py"
spec = importlib.util.spec_from_file_location("instrumentacao_image_manager", MODULE_PATH)
assert spec and spec.loader
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


def _touch(path: Path, data: bytes = b"fake-image") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class FakeClassifier:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def classify(self, path: Path):
        self.calls.append(path)
        return self.result


def confident(label="sensor"):
    return manager.Classification(label, 0.72, "cabos_conectores", 0.16, 0.56, False, "")


def review():
    return manager.Classification("revisar", 0.31, "sensor", 0.28, 0.03, True, "classes_ambiguas")


def test_discovery_requires_fotos_before_instrumentacao(tmp_path: Path) -> None:
    good = tmp_path / "P1" / "Fotos" / "campanha" / "Instrumentação"
    bad = tmp_path / "P2" / "Instrumentação"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    found = manager.discover_instrumentation_dirs(tmp_path)
    assert good in found
    assert bad not in found


def test_only_images_in_target_hierarchy_are_seen(tmp_path: Path) -> None:
    good = _touch(tmp_path / "P1" / "Fotos" / "Instrumentação" / "pod" / "a.JPG")
    _touch(tmp_path / "P1" / "Fotos" / "b.JPG")
    _touch(tmp_path / "P2" / "Instrumentação" / "c.JPG")
    _touch(tmp_path / "P1" / "Fotos" / "Instrumentação" / "pod" / "notas.txt")
    assert list(manager.iter_images(tmp_path)) == [good]


def test_accent_and_case_are_normalized(tmp_path: Path) -> None:
    image = _touch(tmp_path / "p" / "FOTOS" / "x" / "INSTRUMENTAÇÃO" / "pod" / "a.heic")
    assert manager.is_inside_target_hierarchy(image, tmp_path)
    assert manager.inspection_id(image, tmp_path) == "pod"


def test_class_file_is_configurable(tmp_path: Path) -> None:
    classes = tmp_path / "classes.json"
    classes.write_text('[{"label":"Sensor X","description":"sensor x"},{"label":"Cabo","description":"cabo"}]', encoding="utf-8")
    loaded = manager.load_classes(classes)
    assert [item.label for item in loaded] == ["sensor_x", "cabo"]


def test_confident_classification_builds_class_based_name(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    result = confident("sensor")
    target = manager._next_target(image, tmp_path, result, manager.DEFAULT_TEMPLATE)
    assert target.parent == image.parent
    assert target.name.startswith("sensor_pod_")


def test_review_classification_cannot_be_applied(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    target = image.with_name("revisar_pod_20260731_120000_001.jpg")
    with pytest.raises(manager.SafetyError):
        manager.apply_plan(manager.RenamePlan(image, target, review()), tmp_path)
    assert image.exists()


def test_confident_apply_renames_in_same_folder(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    target = image.with_name("sensor_pod_20260731_120000_001.jpg")
    manager.apply_plan(manager.RenamePlan(image, target, confident()), tmp_path)
    assert target.exists()
    assert not image.exists()


def test_apply_cannot_move_between_folders(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    target = tmp_path / "P" / "Fotos" / "Instrumentação" / "motor" / "sensor_motor_20260731_120000_001.jpg"
    target.parent.mkdir(parents=True)
    with pytest.raises(manager.SafetyError):
        manager.apply_plan(manager.RenamePlan(image, target, confident()), tmp_path)


def test_process_existing_sends_only_eligible_image_to_classifier(tmp_path: Path) -> None:
    good = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    _touch(tmp_path / "P" / "Fotos" / "IMG_2.jpg")
    fake = FakeClassifier(confident())
    manifest = tmp_path / "result.csv"
    classified, renamed, needs_review = manager.process_existing(
        tmp_path,
        fake,
        template=manager.DEFAULT_TEMPLATE,
        manifest=manifest,
        apply=False,
        cache=None,
    )
    assert classified == 1
    assert renamed == 0
    assert needs_review == 0
    assert fake.calls == [good]
    text = manifest.read_text(encoding="utf-8-sig")
    assert "sensor" in text
    assert "PREVIA_RENAME" in text


def test_review_goes_to_manifest_and_file_stays_untouched(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    fake = FakeClassifier(review())
    manifest = tmp_path / "result.csv"
    _, renamed, needs_review = manager.process_existing(
        tmp_path,
        fake,
        template=manager.DEFAULT_TEMPLATE,
        manifest=manifest,
        apply=True,
        cache=None,
    )
    assert renamed == 0
    assert needs_review == 1
    assert image.exists()
    assert "REVISAR" in manifest.read_text(encoding="utf-8-sig")


def test_cache_avoids_duplicate_visual_processing(tmp_path: Path) -> None:
    image = _touch(tmp_path / "P" / "Fotos" / "Instrumentação" / "pod" / "IMG_1.jpg")
    fake = FakeClassifier(confident())
    cache = manager.ClassificationCache(tmp_path / "cache.json")
    first = manager.classify_image(image, fake, cache)
    second = manager.classify_image(image, fake, cache)
    assert first == second
    assert fake.calls == [image]


def test_instrumentacao_outside_fotos_is_never_classified(tmp_path: Path) -> None:
    _touch(tmp_path / "P" / "Instrumentação" / "IMG_1.jpg")
    fake = FakeClassifier(confident())
    manager.process_existing(
        tmp_path,
        fake,
        template=manager.DEFAULT_TEMPLATE,
        manifest=tmp_path / "m.csv",
        apply=False,
        cache=None,
    )
    assert fake.calls == []
