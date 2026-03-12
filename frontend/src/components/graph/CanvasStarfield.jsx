import { useEffect, useRef, memo } from 'react';

/**
 * Canvas-based starfield background.
 * Replaces the 100 Framer Motion DOM nodes with a single <canvas> element.
 * Renders 160 stars in 3 size classes with a grouped alpha pulse.
 */
function CanvasStarfieldInner({ className = '' }) {
    const canvasRef = useRef(null);
    const starsRef = useRef(null);
    const animFrameRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;

        function resize() {
            const rect = canvas.parentElement?.getBoundingClientRect() || { width: 800, height: 600 };
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            canvas.style.width = `${rect.width}px`;
            canvas.style.height = `${rect.height}px`;
            ctx.scale(dpr, dpr);
        }

        resize();

        // Generate stars once
        if (!starsRef.current) {
            const stars = [];
            const count = 160;
            for (let i = 0; i < count; i++) {
                // 3 size classes: 60% 1px, 30% 1.5px, 10% 2px
                let size;
                if (i < count * 0.6) size = 1;
                else if (i < count * 0.9) size = 1.5;
                else size = 2;

                stars.push({
                    x: Math.random(),
                    y: Math.random(),
                    size,
                    color: Math.random() < 0.9 ? '#FFFFFF' : '#94A3B8',
                    cohort: i % 3, // 3 animation cohorts offset by 120°
                    baseAlpha: 0.15 + Math.random() * 0.35,
                });
            }
            starsRef.current = stars;
        }

        const stars = starsRef.current;

        function draw(time) {
            const rect = canvas.parentElement?.getBoundingClientRect() || { width: 800, height: 600 };
            const w = rect.width;
            const h = rect.height;

            ctx.clearRect(0, 0, w, h);

            for (let i = 0; i < stars.length; i++) {
                const star = stars[i];
                // Grouped pulse: 3 cohorts offset by 2π/3
                const phase = (time / 2500) + (star.cohort * (Math.PI * 2) / 3);
                const pulse = 0.5 + 0.5 * Math.sin(phase);
                const alpha = star.baseAlpha * (0.4 + 0.6 * pulse);

                ctx.globalAlpha = alpha;
                ctx.fillStyle = star.color;
                ctx.fillRect(
                    star.x * w,
                    star.y * h,
                    star.size,
                    star.size
                );
            }

            ctx.globalAlpha = 1;
            animFrameRef.current = requestAnimationFrame(draw);
        }

        animFrameRef.current = requestAnimationFrame(draw);

        const resizeObserver = new ResizeObserver(resize);
        if (canvas.parentElement) {
            resizeObserver.observe(canvas.parentElement);
        }

        return () => {
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
            resizeObserver.disconnect();
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className={`absolute inset-0 pointer-events-none ${className}`}
            style={{ zIndex: 0 }}
        />
    );
}

export const CanvasStarfield = memo(CanvasStarfieldInner);
