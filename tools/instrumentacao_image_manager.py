#!/usr/bin/env python3
"""Classifica e renomeia imagens SOMENTE em Projetos/.../Fotos/.../Instrumentação/....

Author: mari-2215

Hierarquia obrigatória:
    <root>/.../Fotos/.../Instrumentação/.../<imagem>

Fluxo:
1. percorre a raiz de Projetos procurando diretórios chamados Fotos;
2. dentro de cada Fotos procura Instrumentação/Instrumentacao;
3. abre as imagens elegíveis e executa classificação visual local (CLIP);
4. grava um manifesto CSV com classe, pontuação, margem e decisão;
5. em `apply`, renomeia SOMENTE classificações confiáveis e no mesmo diretório.

Nenhuma imagem fora de Fotos -> Instrumentação pode ser alterada.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol, Sequence

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"
}
FOTOS_COMPONENT = "fotos"
INSTRUMENTATION_COMPONENT = "instrumentacao"
DEFAULT_ROOT = Path(r"\\LABOCEANOSERVER\laboceano\Projetos")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSES_FILE = PROJECT_ROOT / "config" / "classes.json"
DEFAULT_MANIFEST = Path("classification_manifest.csv")
DEFAULT_TEMPLATE = "{class}_{inspection}_{date}_{time}_{seq:03d}"
DEFAULT_MODEL = "openai/clip-vit-base-patch32"
ALREADY_RENAMED = re.compile(r"^.+_\d{8}_\d{6}_\d{3}$")


class SafetyError(RuntimeError):
    """Raised when a filesystem mutation would violate the allowed boundary."""


class ClassificationError(RuntimeError):
    """Raised when an image cannot be classified."""


@dataclass(frozen=True)
class ImageClass:
    label: str
    description: str


@dataclass(frozen=True)
class Classification:
    label: str
    score: float
    second_label: str
    second_score: float
    margin: float
    review_required: bool
    reason: str = ""


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    target: Path
    classification: Classification


class ImageClassifier(Protocol):
    def classify(self, path: Path) -> Classification: ...


def _normalize_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _sanitize_token(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_-. ")
    return value.casefold() or "desconhecido"


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return _canonical(path).relative_to(_canonical(root)).parts
    except ValueError as exc:
        raise SafetyError(f"Caminho fora da raiz permitida: {path}") from exc


def _target_indexes(path: Path, root: Path) -> tuple[tuple[str, ...], int, int]:
    """Return (parts, fotos_index, instrumentation_index) for an approved file path."""
    parts = _relative_parts(path, root)
    directory_parts = parts[:-1]
    fotos_indexes = [
        i for i, part in enumerate(directory_parts)
        if _normalize_component(part) == FOTOS_COMPONENT
    ]
    valid_pairs: list[tuple[int, int]] = []
    for instr_idx, part in enumerate(directory_parts):
        if _normalize_component(part) != INSTRUMENTATION_COMPONENT:
            continue
        preceding = [idx for idx in fotos_indexes if idx < instr_idx]
        if preceding:
            valid_pairs.append((preceding[-1], instr_idx))
    if not valid_pairs:
        raise SafetyError(
            f"Recusado: {path} não segue a hierarquia Fotos/.../Instrumentação"
        )
    fotos_idx, instr_idx = valid_pairs[-1]
    return parts, fotos_idx, instr_idx


def is_inside_target_hierarchy(path: Path, root: Path) -> bool:
    try:
        _target_indexes(path, root)
        return True
    except SafetyError:
        return False


def inspection_id(path: Path, root: Path) -> str:
    """Use the first directory below Instrumentação as an inspection identifier."""
    parts, _fotos_idx, instr_idx = _target_indexes(path, root)
    if instr_idx + 1 < len(parts) - 1:
        return _sanitize_token(parts[instr_idx + 1])
    return "instrumentacao"


def _validate_root(root: Path) -> Path:
    root = _canonical(root)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Raiz inexistente ou inválida: {root}")
    return root


def _safe_walk(root: Path):
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames if not (current_path / name).is_symlink()
        ]
        yield current_path, dirnames, filenames


def discover_fotos_dirs(root: Path) -> list[Path]:
    root = _validate_root(root)
    found: set[Path] = set()
    if _normalize_component(root.name) == FOTOS_COMPONENT:
        return [root]
    for current, dirnames, _filenames in _safe_walk(root):
        for name in list(dirnames):
            if _normalize_component(name) == FOTOS_COMPONENT:
                candidate = current / name
                found.add(candidate)
                # Stage 2 owns the Fotos subtree.
                dirnames.remove(name)
    return sorted(found, key=lambda p: str(p).casefold())


def discover_instrumentation_dirs(root: Path) -> list[Path]:
    root = _validate_root(root)
    found: set[Path] = set()
    for fotos_dir in discover_fotos_dirs(root):
        for current, dirnames, _filenames in _safe_walk(fotos_dir):
            for name in list(dirnames):
                if _normalize_component(name) == INSTRUMENTATION_COMPONENT:
                    candidate = current / name
                    found.add(candidate)
                    # Later recursion scans every image below this directory.
                    dirnames.remove(name)
    return sorted(found, key=lambda p: str(p).casefold())


def iter_images_in_targets(root: Path, targets: Sequence[Path]) -> Iterable[Path]:
    root = _canonical(root)
    seen: set[Path] = set()
    for target_dir in targets:
        target_dir = _canonical(target_dir)
        for current, _dirnames, filenames in _safe_walk(target_dir):
            for filename in filenames:
                path = current / filename
                if path.is_symlink() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                canonical = _canonical(path)
                if canonical in seen:
                    continue
                if is_inside_target_hierarchy(canonical, root):
                    seen.add(canonical)
                    yield canonical


def iter_images(root: Path) -> Iterable[Path]:
    root = _validate_root(root)
    targets = discover_instrumentation_dirs(root)
    yield from iter_images_in_targets(root, targets)


def load_classes(path: Path) -> list[ImageClass]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("O arquivo de classes precisa conter pelo menos duas classes")
    classes: list[ImageClass] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict) or not item.get("label") or not item.get("description"):
            raise ValueError("Cada classe precisa de 'label' e 'description'")
        label = _sanitize_token(str(item["label"]))
        if label in seen:
            raise ValueError(f"Classe duplicada: {label}")
        seen.add(label)
        classes.append(ImageClass(label, str(item["description"]).strip()))
    return classes


class ClipClassifier:
    """Local zero-shot visual classifier backed by a Hugging Face CLIP pipeline."""

    def __init__(
        self,
        classes: Sequence[ImageClass],
        *,
        model: str = DEFAULT_MODEL,
        min_score: float = 0.35,
        min_margin: float = 0.08,
        device: int = -1,
    ) -> None:
        self.classes = list(classes)
        self.min_score = min_score
        self.min_margin = min_margin
        self.model_name = model
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise ClassificationError(
                "Dependência ausente. Instale requirements.txt antes de classificar."
            ) from exc
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        self._pipeline = pipeline(
            task="zero-shot-image-classification",
            model=model,
            device=device,
        )
        self._candidate_to_label = {
            self._candidate_text(item): item.label for item in self.classes
        }

    @staticmethod
    def _candidate_text(item: ImageClass) -> str:
        return f"{item.label.replace('_', ' ')}: {item.description}"

    def classify(self, path: Path) -> Classification:
        candidates = [self._candidate_text(item) for item in self.classes]
        try:
            results = self._pipeline(
                str(path),
                candidate_labels=candidates,
                hypothesis_template="Esta é uma foto de {}.",
            )
        except Exception as exc:  # Model/image backends raise heterogeneous exceptions.
            return Classification(
                label="revisar",
                score=0.0,
                second_label="",
                second_score=0.0,
                margin=0.0,
                review_required=True,
                reason=f"falha_classificacao: {type(exc).__name__}: {exc}",
            )
        if not results:
            return Classification("revisar", 0.0, "", 0.0, 0.0, True, "sem_resultado")

        ordered = sorted(results, key=lambda item: float(item.get("score", 0.0)), reverse=True)
        first = ordered[0]
        second = ordered[1] if len(ordered) > 1 else {"label": "", "score": 0.0}
        first_label = self._candidate_to_label.get(str(first.get("label", "")), "outro")
        second_label = self._candidate_to_label.get(str(second.get("label", "")), "")
        score = float(first.get("score", 0.0))
        second_score = float(second.get("score", 0.0))
        margin = score - second_score
        review = score < self.min_score or margin < self.min_margin or first_label == "outro"
        reasons: list[str] = []
        if score < self.min_score:
            reasons.append("pontuacao_baixa")
        if margin < self.min_margin:
            reasons.append("classes_ambiguas")
        if first_label == "outro":
            reasons.append("classe_outro")
        return Classification(
            label="revisar" if review else first_label,
            score=score,
            second_label=second_label,
            second_score=second_score,
            margin=margin,
            review_required=review,
            reason=";".join(reasons),
        )


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    payload = f"{_canonical(path)}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ClassificationCache:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, dict[str, object]] = {}
        if path and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = raw
            except (OSError, json.JSONDecodeError):
                self.data = {}

    def get(self, image: Path) -> Classification | None:
        item = self.data.get(_fingerprint(image))
        if not isinstance(item, dict):
            return None
        try:
            return Classification(**item)
        except TypeError:
            return None

    def put(self, image: Path, result: Classification) -> None:
        self.data[_fingerprint(image)] = asdict(result)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def classify_image(
    path: Path,
    classifier: ImageClassifier,
    cache: ClassificationCache | None = None,
) -> Classification:
    if cache:
        cached = cache.get(path)
        if cached:
            return cached
    result = classifier.classify(path)
    if cache:
        cache.put(path, result)
    return result


def _format_stem(
    path: Path,
    root: Path,
    classification: Classification,
    seq: int,
    template: str,
) -> str:
    dt = datetime.fromtimestamp(path.stat().st_mtime)
    fields = {
        "class": classification.label,
        "inspection": inspection_id(path, root),
        "date": dt.strftime("%Y%m%d"),
        "time": dt.strftime("%H%M%S"),
        "datetime": dt.strftime("%Y%m%d_%H%M%S"),
        "seq": seq,
        "stem": _sanitize_token(path.stem),
    }
    try:
        stem = template.format(**fields)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Template inválido: {template!r}") from exc
    return _sanitize_token(stem)


def _next_target(
    path: Path,
    root: Path,
    classification: Classification,
    template: str,
) -> Path:
    for seq in range(1, 10000):
        stem = _format_stem(path, root, classification, seq, template)
        candidate = path.with_name(stem + path.suffix.casefold())
        if candidate == path or not candidate.exists():
            return candidate
    raise RuntimeError(f"Não foi possível encontrar um nome livre para {path}")


def apply_plan(plan: RenamePlan, root: Path) -> None:
    root = _canonical(root)
    source = _canonical(plan.source)
    target = _canonical(plan.target)
    if plan.classification.review_required:
        raise SafetyError("Classificação marcada para revisão não pode ser aplicada automaticamente")
    if not is_inside_target_hierarchy(source, root):
        raise SafetyError(f"Origem recusada fora de Fotos/.../Instrumentação: {source}")
    if not is_inside_target_hierarchy(target, root):
        raise SafetyError(f"Destino recusado fora de Fotos/.../Instrumentação: {target}")
    if source.parent != target.parent:
        raise SafetyError("O programa só pode renomear; mover arquivos entre pastas é proibido")
    if source.is_symlink():
        raise SafetyError("Links simbólicos não são alterados")
    if target.exists() and target != source:
        raise FileExistsError(f"Destino já existe: {target}")
    source.rename(target)


def write_manifest(rows: Sequence[dict[str, object]], manifest: Path) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source", "suggested_name", "class", "score", "second_class",
        "second_score", "margin", "review_required", "reason", "action"
    ]
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def process_existing(
    root: Path,
    classifier: ImageClassifier,
    *,
    template: str,
    manifest: Path,
    apply: bool,
    cache: ClassificationCache | None,
    include_already_renamed: bool = False,
) -> tuple[int, int, int]:
    root = _validate_root(root)
    images = sorted(
        iter_images(root),
        key=lambda p: (str(p.parent).casefold(), p.stat().st_mtime_ns, p.name.casefold()),
    )
    rows: list[dict[str, object]] = []
    classified = renamed = review = 0

    for source in images:
        if not include_already_renamed and ALREADY_RENAMED.fullmatch(source.stem):
            continue
        result = classify_image(source, classifier, cache)
        classified += 1
        if result.review_required:
            review += 1
            target = source
            action = "REVISAR"
        else:
            target = _next_target(source, root, result, template)
            action = "RENOMEAR" if apply else "PREVIA_RENAME"
            if apply:
                apply_plan(RenamePlan(source, target, result), root)
                renamed += 1

        rows.append({
            "source": str(source),
            "suggested_name": target.name if target != source else "",
            "class": result.label,
            "score": f"{result.score:.6f}",
            "second_class": result.second_label,
            "second_score": f"{result.second_score:.6f}",
            "margin": f"{result.margin:.6f}",
            "review_required": result.review_required,
            "reason": result.reason,
            "action": action,
        })
        print(
            f"[{action}] {source} -> {result.label} "
            f"(score={result.score:.3f}, margem={result.margin:.3f})"
            + (f" -> {target.name}" if target != source else "")
        )

    write_manifest(rows, manifest)
    if cache:
        cache.save()
    return classified, renamed, review


def watch(
    root: Path,
    classifier: ImageClassifier,
    *,
    template: str,
    interval: float,
    settle_seconds: float,
    rediscover_seconds: float,
    manifest: Path,
    cache: ClassificationCache | None,
) -> None:
    root = _validate_root(root)
    targets = discover_instrumentation_dirs(root)
    known = {p for p in iter_images_in_targets(root, targets)}
    pending: dict[Path, tuple[int, int, float]] = {}
    rows: list[dict[str, object]] = []
    last_discovery = time.monotonic()

    print(f"Monitorando: {root}")
    print(f"Instrumentação válida dentro de Fotos: {len(targets)} pasta(s)")
    print(f"{len(known)} imagem(ns) existentes ignoradas. Ctrl+C para sair.")

    while True:
        now = time.monotonic()
        if now - last_discovery >= rediscover_seconds:
            targets = discover_instrumentation_dirs(root)
            last_discovery = now

        current = {p for p in iter_images_in_targets(root, targets)}
        new_paths = current - known
        for path in list(pending):
            if path not in current:
                pending.pop(path, None)

        for path in new_paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            fingerprint = (stat.st_size, stat.st_mtime_ns)
            previous = pending.get(path)
            if previous is None or previous[:2] != fingerprint:
                pending[path] = (fingerprint[0], fingerprint[1], now)
                continue
            if now - previous[2] < settle_seconds:
                continue

            result = classify_image(path, classifier, cache)
            target = path
            action = "REVISAR"
            if not result.review_required:
                target = _next_target(path, root, result, template)
                apply_plan(RenamePlan(path, target, result), root)
                action = "RENOMEADO"
                known.add(_canonical(target))
            else:
                known.add(path)
            known.discard(path if target != path else Path("__never__"))
            pending.pop(path, None)
            rows.append({
                "source": str(path),
                "suggested_name": target.name if target != path else "",
                "class": result.label,
                "score": f"{result.score:.6f}",
                "second_class": result.second_label,
                "second_score": f"{result.second_score:.6f}",
                "margin": f"{result.margin:.6f}",
                "review_required": result.review_required,
                "reason": result.reason,
                "action": action,
            })
            write_manifest(rows, manifest)
            if cache:
                cache.save()
            print(f"[{action}] {path.name} -> {result.label}")

        known &= current | {p for p in known if p.exists()}
        time.sleep(interval)


def _default_cache_path() -> Path:
    return Path.home() / ".cache" / "instrumentation_image_manager" / "classifications.json"


def make_classifier(args: argparse.Namespace) -> ImageClassifier:
    classes = load_classes(args.classes)
    if args.classifier == "clip":
        return ClipClassifier(
            classes,
            model=args.model,
            min_score=args.min_score,
            min_margin=args.min_margin,
            device=args.device,
        )
    raise ValueError(f"Classificador desconhecido: {args.classifier}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "LABOCEANO: Projetos -> Fotos -> Instrumentação -> análise visual -> "
            "manifesto -> rename seguro."
        )
    )
    parser.add_argument("mode", choices=("discover", "scan", "classify", "apply", "watch"))
    parser.add_argument("root", type=Path, nargs="?", default=DEFAULT_ROOT)
    parser.add_argument("--classes", type=Path, default=DEFAULT_CLASSES_FILE)
    parser.add_argument("--classifier", choices=("clip",), default="clip")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", type=int, default=-1, help="-1=CPU; 0=primeira GPU CUDA")
    parser.add_argument("--min-score", type=float, default=0.35)
    parser.add_argument("--min-margin", type=float, default=0.08)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache", type=Path, default=_default_cache_path())
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--include-already-renamed", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--rediscover-seconds", type=float, default=60.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "discover":
        root = _validate_root(args.root)
        fotos = discover_fotos_dirs(root)
        instrumentation = discover_instrumentation_dirs(root)
        images = list(iter_images_in_targets(root, instrumentation))
        print(f"Raiz: {root}")
        print(f"Fotos: {len(fotos)}")
        print(f"Instrumentação dentro de Fotos: {len(instrumentation)}")
        print(f"Imagens elegíveis: {len(images)}")
        for item in instrumentation:
            print(f"  {item}")
        return

    if not (0.0 <= args.min_score <= 1.0 and 0.0 <= args.min_margin <= 1.0):
        raise SystemExit("--min-score e --min-margin devem estar entre 0 e 1")
    classifier = make_classifier(args)
    cache = None if args.no_cache else ClassificationCache(args.cache)

    if args.mode == "watch":
        try:
            watch(
                args.root,
                classifier,
                template=args.template,
                interval=args.interval,
                settle_seconds=args.settle_seconds,
                rediscover_seconds=args.rediscover_seconds,
                manifest=args.manifest,
                cache=cache,
            )
        except KeyboardInterrupt:
            print("\nMonitoramento encerrado.")
        return

    apply = args.mode == "apply"
    classified, renamed, review = process_existing(
        args.root,
        classifier,
        template=args.template,
        manifest=args.manifest,
        apply=apply,
        cache=cache,
        include_already_renamed=args.include_already_renamed,
    )
    print(f"\nClassificadas: {classified} | Renomeadas: {renamed} | Revisar: {review}")
    print(f"Manifesto: {args.manifest.resolve()}")
    if not apply:
        print("Nenhum arquivo foi renomeado. Use 'apply' somente após revisar o manifesto.")


if __name__ == "__main__":
    main()
