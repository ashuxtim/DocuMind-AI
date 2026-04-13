import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Search, X } from 'lucide-react';

const PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
const WORKER_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

/**
 * PDFViewer — Renders all pages of a PDF using PDF.js with
 * scroll-synced page tracking, zoom controls, page navigation,
 * and in-document keyword search.
 *
 * Props:
 *   filename — the document filename to render
 */
const PDFViewer = forwardRef(function PDFViewer({ filename }, ref) {
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [currentMatch, setCurrentMatch] = useState(0);
  const [showSearch, setShowSearch] = useState(false);

  const pdfRef = useRef(null);
  const pageRefs = useRef([]);
  const containerRef = useRef(null);
  const observerRef = useRef(null);
  const debounceRef = useRef(null);
  const searchInputRef = useRef(null);

  // ── Expose scrollToPage to parent via ref ──
  useImperativeHandle(ref, () => ({
    scrollToPage(pageNum) {
      pageRefs.current[pageNum - 1]?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    },
  }));

  // ── Load PDF.js + document ──
  useEffect(() => {
    if (!filename) return;

    setLoading(true);
    setError(null);
    setCurrentPage(1);
    setNumPages(0);
    pdfRef.current = null;
    pageRefs.current = [];

    const loadPDF = async () => {
      try {
        if (!window.pdfjsLib) {
          await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = PDFJS_CDN;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
          });
          window.pdfjsLib.GlobalWorkerOptions.workerSrc = WORKER_CDN;
        }

        const pdf = await window.pdfjsLib.getDocument(
          `/api/uploads/${filename}`
        ).promise;
        pdfRef.current = pdf;
        setNumPages(pdf.numPages);
        setLoading(false);
      } catch (e) {
        console.error('[PDFViewer] Load failed:', e);
        setError('Failed to load PDF');
        setLoading(false);
      }
    };

    loadPDF();
  }, [filename]);

  // ── Render ALL pages + set up IntersectionObserver ──
  useEffect(() => {
    if (!pdfRef.current || numPages === 0) return;

    const renderAllPages = async () => {
      for (let i = 1; i <= numPages; i++) {
        const canvas = pageRefs.current[i - 1];
        if (!canvas) continue;

        const page = await pdfRef.current.getPage(i);
        const dpr = window.devicePixelRatio || 1;
        const containerWidth = containerRef.current
          ? containerRef.current.clientWidth - 48
          : 600;

        const baseViewport = page.getViewport({ scale: 1 });
        const fitScale = (containerWidth / baseViewport.width) * scale;
        const renderScale = fitScale * dpr;

        const viewport = page.getViewport({ scale: fitScale });
        const renderViewport = page.getViewport({ scale: renderScale });

        canvas.width = renderViewport.width;
        canvas.height = renderViewport.height;
        canvas.style.width = viewport.width + 'px';
        canvas.style.height = viewport.height + 'px';

        const ctx = canvas.getContext('2d');
        await page.render({
          canvasContext: ctx,
          viewport: renderViewport,
        }).promise;
      }

      // Set up IntersectionObserver after all pages are rendered
      if (observerRef.current) observerRef.current.disconnect();

      observerRef.current = new IntersectionObserver(
        (entries) => {
          let maxRatio = 0;
          let visiblePage = null;
          entries.forEach((entry) => {
            if (entry.intersectionRatio > maxRatio) {
              maxRatio = entry.intersectionRatio;
              const idx = pageRefs.current.indexOf(entry.target);
              if (idx !== -1) visiblePage = idx + 1;
            }
          });
          if (visiblePage === null) return;
          if (debounceRef.current) clearTimeout(debounceRef.current);
          debounceRef.current = setTimeout(() => {
            setCurrentPage(visiblePage);
          }, 150);
        },
        {
          root: containerRef.current,
          threshold: Array.from({ length: 11 }, (_, i) => i / 10),
        }
      );

      pageRefs.current.forEach((canvas) => {
        if (canvas) observerRef.current.observe(canvas);
      });
    };

    renderAllPages();
  }, [numPages, scale]);

  // ── Cleanup observer + debounce on unmount ──
  useEffect(() => {
    return () => {
      if (observerRef.current) observerRef.current.disconnect();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // ── Zoom handlers ──
  const zoomIn = useCallback(
    () => setScale((s) => Math.min(2.0, parseFloat((s + 0.25).toFixed(2)))),
    []
  );
  const zoomOut = useCallback(
    () => setScale((s) => Math.max(0.5, parseFloat((s - 0.25).toFixed(2)))),
    []
  );

  // ── Page navigation handlers ──
  const goToPrev = useCallback(() => {
    const target = pageRefs.current[currentPage - 2];
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [currentPage]);

  const goToNext = useCallback(() => {
    const target = pageRefs.current[currentPage];
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [currentPage]);

  const jumpToPage = useCallback(
    (e) => {
      const val = parseInt(e.target.value);
      if (!isNaN(val) && val >= 1 && val <= numPages) {
        pageRefs.current[val - 1]?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }
    },
    [numPages]
  );

  // ── Search logic ──
  const searchInPDF = useCallback(async (query) => {
    if (!pdfRef.current || !query.trim()) {
      setSearchResults([]);
      setCurrentMatch(0);
      return;
    }

    const results = [];
    for (let i = 1; i <= numPages; i++) {
      const page = await pdfRef.current.getPage(i);
      const textContent = await page.getTextContent();
      const text = textContent.items
        .map((item) => item.str)
        .join(' ')
        .toLowerCase();

      const q = query.toLowerCase();
      let idx = text.indexOf(q);
      let matchIndex = 0;
      while (idx !== -1) {
        results.push({ pageNum: i, matchIndex });
        idx = text.indexOf(q, idx + 1);
        matchIndex++;
      }
    }

    setSearchResults(results);
    setCurrentMatch(0);

    if (results.length > 0) {
      pageRefs.current[results[0].pageNum - 1]
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [numPages]);

  const goToNextMatch = useCallback(() => {
    if (searchResults.length === 0) return;
    const next = (currentMatch + 1) % searchResults.length;
    setCurrentMatch(next);
    pageRefs.current[searchResults[next].pageNum - 1]
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [searchResults, currentMatch]);

  const goToPrevMatch = useCallback(() => {
    if (searchResults.length === 0) return;
    const prev = (currentMatch - 1 + searchResults.length) % searchResults.length;
    setCurrentMatch(prev);
    pageRefs.current[searchResults[prev].pageNum - 1]
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [searchResults, currentMatch]);

  // ── Debounced search trigger ──
  useEffect(() => {
    const t = setTimeout(() => {
      searchInPDF(searchQuery);
    }, 400);
    return () => clearTimeout(t);
  }, [searchQuery, searchInPDF]);

  // ── Escape to close search ──
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false);
        setSearchQuery('');
        setSearchResults([]);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [showSearch]);

  // ── Focus search input when opened ──
  useEffect(() => {
    if (showSearch) {
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
  }, [showSearch]);

  // ── Render ──
  return (
    <div className="relative flex flex-col h-full overflow-hidden">

      {/* ── Scrollable canvas area ── */}
      <div ref={containerRef} className="flex-1 min-h-0 overflow-y-auto overflow-x-auto bg-zinc-900 px-6 pb-16 pt-4">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-muted-foreground">Loading PDF…</p>
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        {!loading && !error && (
          <div className="flex flex-col gap-4 items-start w-fit mx-auto">
            {Array.from({ length: numPages }, (_, i) => (
              <canvas
                key={i}
                ref={(el) => (pageRefs.current[i] = el)}
                className="shadow-xl rounded-sm"
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Search bar overlay (top) ── */}
      {showSearch && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-2 rounded-full bg-zinc-800/90 backdrop-blur-sm border border-zinc-700/50 shadow-lg z-10 w-72">
          <Search className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search in document..."
            className="flex-1 bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 border-0 focus:outline-none"
          />
          {searchResults.length > 0 && (
            <span className="text-[10px] text-zinc-400 whitespace-nowrap">
              {currentMatch + 1}/{searchResults.length}
            </span>
          )}
          {searchQuery && searchResults.length === 0 && (
            <span className="text-[10px] text-zinc-500 whitespace-nowrap">
              No results
            </span>
          )}
          {searchResults.length > 1 && (
            <>
              <button
                onClick={goToPrevMatch}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-700 text-zinc-400"
              >
                <ChevronLeft className="w-3 h-3" />
              </button>
              <button
                onClick={goToNextMatch}
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-700 text-zinc-400"
              >
                <ChevronRight className="w-3 h-3" />
              </button>
            </>
          )}
          <button
            onClick={() => {
              setShowSearch(false);
              setSearchQuery('');
              setSearchResults([]);
            }}
            className="w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-700 text-zinc-400"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* ── Floating bottom bar ── */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-3 px-4 py-2 rounded-full bg-zinc-800/90 backdrop-blur-sm border border-zinc-700/50 shadow-lg z-10">
        {/* Page controls */}
        <button
          onClick={goToPrev}
          disabled={currentPage <= 1}
          className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-700 disabled:opacity-30 transition-colors text-zinc-300"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-1.5 text-xs text-zinc-300 whitespace-nowrap">
          <input
            type="number"
            defaultValue={currentPage}
            key={currentPage}
            onBlur={jumpToPage}
            onKeyDown={(e) => e.key === 'Enter' && jumpToPage(e)}
            className="w-12 text-center text-xs bg-zinc-700 rounded-md px-1 py-0.5 border-0 focus:outline-none focus:ring-1 focus:ring-zinc-500 text-zinc-100 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            style={{ width: '48px' }}
            min={1}
            max={numPages}
          />
          {numPages > 0 && <span className="text-zinc-400 flex-shrink-0">/ {numPages}</span>}
        </div>

        <button
          onClick={goToNext}
          disabled={currentPage >= numPages}
          className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-700 disabled:opacity-30 transition-colors text-zinc-300"
        >
          <ChevronRight className="w-4 h-4" />
        </button>

        {/* Divider */}
        <div className="w-px h-4 bg-zinc-600" />

        {/* Zoom controls */}
        <button
          onClick={zoomOut}
          disabled={scale <= 0.5}
          className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-700 disabled:opacity-30 transition-colors text-zinc-300"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>

        <span className="text-xs text-zinc-400 w-9 text-center">
          {Math.round(scale * 100)}%
        </span>

        <button
          onClick={zoomIn}
          disabled={scale >= 2.0}
          className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-700 disabled:opacity-30 transition-colors text-zinc-300"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>

        {/* Divider */}
        <div className="w-px h-4 bg-zinc-600" />

        {/* Search toggle */}
        <button
          onClick={() => setShowSearch((s) => !s)}
          className={`w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-700 transition-colors ${
            showSearch ? 'text-primary bg-zinc-700' : 'text-zinc-300'
          }`}
        >
          <Search className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
});

export default PDFViewer;
