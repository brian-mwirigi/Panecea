"use client";

/**
 * Client-side PDF text extraction using pdf.js.
 *
 * The backend's server-side extractor (pypdf) frequently returns little or no
 * text even for PDFs whose text is visually selectable (missing ToUnicode maps,
 * unusual encodings, etc.). pdf.js is the same engine browsers use to render
 * selectable text, so extracting here is dramatically more reliable. We then
 * hand the clean text straight to /agent/run and skip server-side parsing.
 */

// Loaded lazily so pdf.js never runs during SSR / build. We use the *legacy*
// build, which is transpiled for broad browser support (Safari/WebKit and older
// engines) — the default build uses newer JS that some browsers choke on with
// "undefined is not a function".
type PdfjsModule = typeof import("pdfjs-dist");
let pdfjsPromise: Promise<PdfjsModule> | null = null;

async function loadPdfjs(): Promise<PdfjsModule> {
  if (!pdfjsPromise) {
    pdfjsPromise = import("pdfjs-dist/legacy/build/pdf.mjs").then((mod) => {
      const pdfjs = mod as unknown as PdfjsModule;
      pdfjs.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
      return pdfjs;
    });
  }
  return pdfjsPromise;
}

/** Extract all text from a PDF file in the browser. Returns normalized text. */
export async function extractPdfText(file: File): Promise<string> {
  const pdfjs = await loadPdfjs();
  const data = new Uint8Array(await file.arrayBuffer());
  const loadingTask = pdfjs.getDocument({ data });
  const doc = await loadingTask.promise;

  try {
    const pages: string[] = [];
    for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
      const page = await doc.getPage(pageNum);
      const content = await page.getTextContent();
      const line = content.items
        .map((item) => ("str" in item ? item.str : ""))
        .join(" ");
      pages.push(line);
      page.cleanup();
    }
    return pages
      .join("\n\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  } finally {
    await loadingTask.destroy();
  }
}
