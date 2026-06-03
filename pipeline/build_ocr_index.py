#!/usr/bin/env python3
"""
OCR 语义检索索引构建 — output/ → chroma_db_ocr/
727万字教材原文 → 2,000字分段 → bge-large-zh 嵌入 → numpy 存储

用法：
    python pipeline/build_ocr_index.py
    输出：chroma_db_ocr/(embeddings.npy + chunks.pkl)
"""
import json, sys, os, pickle, time, re
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DATA_DIR = Path(os.environ.get("JURIS_OCR_DIR", "./data/ocr_output"))
OUT_DIR = Path(os.environ.get("JURIS_OCR_INDEX_DIR", "./data/chroma_db_ocr"))
OUT_DIR.mkdir(exist_ok=True)
CHUNK_SIZE = 2000  # 每段约 2000 字


def extract_text_from_ocr(fp: Path) -> List[Dict]:
    """从 OCR JSON 提取 (原文, 书名, 页码范围)"""
    data = json.loads(fp.read_text(encoding="utf-8"))
    book_name = fp.name.replace("_ocr.json", "")
    pages = data.get("pages", [])

    chunks = []
    buffer = ""
    start_page = 0

    for page in pages:
        pn = page.get("page", 0)
        text = page.get("text", "").strip()
        if not text:
            continue
        if start_page == 0:
            start_page = pn

        buffer += text + "\n"

        # 按页切段，对齐到段落边界
        while len(buffer) >= CHUNK_SIZE:
            # 找最近的句号/换行作为切分点
            split_at = CHUNK_SIZE
            for sep in ["。", "\n", "；", "；"]:
                idx = buffer.rfind(sep, CHUNK_SIZE // 2, CHUNK_SIZE + 200)
                if idx > 0:
                    split_at = idx + 1
                    break

            chunk_text = buffer[:split_at].strip()
            if chunk_text:
                chunks.append({"text": chunk_text, "book": book_name, "start_page": start_page, "end_page": pn})
            buffer = buffer[split_at:]
            start_page = pn

    # 最后一段
    buffer = buffer.strip()
    if buffer:
        chunks.append({"text": buffer, "book": book_name, "start_page": start_page, "end_page": pages[-1]["page"] if pages else 0})

    return chunks


def main():
    ocr_files = sorted(DATA_DIR.glob("*_ocr.json"))
    print(f"OCR 文件: {len(ocr_files)} 个")

    # 1. 提取并分段
    t0 = time.time()
    all_chunks = []
    for fp in ocr_files:
        chunks = extract_text_from_ocr(fp)
        all_chunks.extend(chunks)
        print(f"  {fp.name}: {len(chunks)} 段")

    print(f"\n总段数: {len(all_chunks)}")
    print(f"提取耗时: {time.time()-t0:.0f}s")

    # 2. 计算嵌入 (CUDA + FP16 加速)
    print("\n加载 bge-large-zh 并启用 CUDA + FP16...")
    from sentence_transformers import SentenceTransformer
    import torch
    model = SentenceTransformer("BAAI/bge-large-zh-v1.5", device="cuda")
    model.half()  # FP16: RTX 3050 支持的半精度推理 (~2x 加速)

    texts = [c["text"][:512] for c in all_chunks]  # 截断到 512 字符

    BATCH = 128  # RTX 3050 4GB 下的最优 batch_size
    print(f"计算 {len(texts)} 段嵌入 (batch_size={BATCH}, CUDA + FP16)...")
    t0 = time.time()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True, batch_size=BATCH)
    print(f"嵌入耗时: {time.time()-t0:.0f}s")
    print(f"嵌入维度: {embeddings.shape}")

    # 3. 保存
    import numpy as np
    meta = [{"book": c["book"], "start_page": c["start_page"], "end_page": c["end_page"], "text": c["text"][:200]} for c in all_chunks]

    np.save(str(OUT_DIR / "embeddings.npy"), embeddings)
    with open(OUT_DIR / "chunks.pkl", "wb") as f:
        pickle.dump(all_chunks, f)
    with open(OUT_DIR / "metadata.pkl", "wb") as f:
        pickle.dump(meta, f)

    size_mb = os.path.getsize(OUT_DIR / "embeddings.npy") / 1e6
    print(f"\n✅ 索引已保存: {OUT_DIR}")
    print(f"  embeddings.npy: {size_mb:.1f}MB")
    print(f"  chunks.pkl: {len(all_chunks)} 段")


if __name__ == "__main__":
    main()
