"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface AnimatedGradientBackgroundProps {
    className?: string;
    children?: React.ReactNode;
    intensity?: "subtle" | "medium" | "strong";
}

interface Beam {
    x: number;
    y: number;
    width: number;
    length: number;
    angle: number;
    speed: number;
    opacity: number;
    hue: number;
    pulse: number;
    pulseSpeed: number;
}

// Narrow blue/purple hue range to match target look
const HUE_MIN = 220;
const HUE_MAX = 260;

function createBeam(width: number, height: number): Beam {
    const angle = -30 + Math.random() * 8; // Reduced randomness
    return {
        x: Math.random() * width * 1.2 - width * 0.1,
        y: Math.random() * height * 1.2 - height * 0.1,
        width: 40 + Math.random() * 40, // Smaller range
        length: height * 1.8, // Reduced length
        angle: angle,
        speed: 0.8 + Math.random() * 0.8, // Faster, smaller range
        opacity: 0.15 + Math.random() * 0.1, // More consistent opacity
        hue: HUE_MIN + Math.random() * (HUE_MAX - HUE_MIN),
        pulse: Math.random() * Math.PI * 2,
        pulseSpeed: 0.025 + Math.random() * 0.02, // Slightly faster pulse
    };
}

export function BeamsBackground({
    className,
    children,
    intensity = "strong",
}: AnimatedGradientBackgroundProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const beamsRef = useRef<Beam[]>([]);
    const animationFrameRef = useRef<number>(0);
    const lastFrameTimeRef = useRef<number>(0);
    const frameCountRef = useRef<number>(0);
    const performanceCheckRef = useRef<number>(0);
    const MINIMUM_BEAMS = 8; // Reduced from 20 for better performance
    const TARGET_FPS = 60;
    const FRAME_INTERVAL = 1000 / TARGET_FPS;
    const PERFORMANCE_CHECK_INTERVAL = 60; // Check every 60 frames

    const opacityMap = {
        subtle: 0.7,
        medium: 0.85,
        strong: 1,
    };

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d", { 
            alpha: true, 
            desynchronized: true,
            willReadFrequently: false 
        });
        if (!ctx) return;

        const updateCanvasSize = () => {
            const dpr = window.devicePixelRatio || 1;
            canvas.width = window.innerWidth * dpr;
            canvas.height = window.innerHeight * dpr;
            canvas.style.width = `${window.innerWidth}px`;
            canvas.style.height = `${window.innerHeight}px`;
            ctx.scale(dpr, dpr);

            const totalBeams = MINIMUM_BEAMS;
            beamsRef.current = Array.from({ length: totalBeams }, () =>
                createBeam(canvas.width, canvas.height)
            );
        };

        updateCanvasSize();
        window.addEventListener("resize", updateCanvasSize);

        function resetBeam(beam: Beam, index: number, totalBeams: number) {
            if (!canvas) return beam;
            
            const column = index % 3;
            const spacing = canvas.width / 3;

            beam.y = canvas.height + 100;
            beam.x =
                column * spacing +
                spacing / 2 +
                (Math.random() - 0.5) * spacing * 0.5;
            beam.width = 100 + Math.random() * 100;
            beam.speed = 0.5 + Math.random() * 0.4;
            beam.hue = HUE_MIN + ((index / totalBeams) * (HUE_MAX - HUE_MIN));
            beam.opacity = 0.2 + Math.random() * 0.1;
            return beam;
        }

        function drawBeam(ctx: CanvasRenderingContext2D, beam: Beam) {
            ctx.save();
            ctx.translate(beam.x, beam.y);
            ctx.rotate((beam.angle * Math.PI) / 180);

            // Calculate pulsing opacity with reduced complexity
            const pulsingOpacity =
                beam.opacity *
                (0.85 + Math.sin(beam.pulse) * 0.15) *
                opacityMap[intensity];

            // Simplified gradient with fewer stops for better performance
            const gradient = ctx.createLinearGradient(0, 0, 0, beam.length);
            gradient.addColorStop(0, `hsla(${beam.hue}, 80%, 60%, 0)`);
            gradient.addColorStop(0.3, `hsla(${beam.hue}, 80%, 60%, ${pulsingOpacity * 0.6})`);
            gradient.addColorStop(0.7, `hsla(${beam.hue}, 80%, 60%, ${pulsingOpacity})`);
            gradient.addColorStop(1, `hsla(${beam.hue}, 80%, 60%, 0)`);

            ctx.fillStyle = gradient;
            ctx.fillRect(-beam.width / 2, 0, beam.width, beam.length);
            ctx.restore();
        }

        function animate(currentTime: number) {
            if (!canvas || !ctx) return;

            // Throttle frame rate for better performance
            if (currentTime - lastFrameTimeRef.current < FRAME_INTERVAL) {
                animationFrameRef.current = requestAnimationFrame(animate);
                return;
            }

            // Performance monitoring
            frameCountRef.current++;
            if (frameCountRef.current % PERFORMANCE_CHECK_INTERVAL === 0) {
                const frameDelta = currentTime - performanceCheckRef.current;
                const avgFrameTime = frameDelta / PERFORMANCE_CHECK_INTERVAL;
                
                // If frame time is too high (>20ms), reduce beam count
                if (avgFrameTime > 20 && beamsRef.current.length > 4) {
                    beamsRef.current = beamsRef.current.slice(0, Math.max(4, beamsRef.current.length - 2));
                }
                
                performanceCheckRef.current = currentTime;
            }

            lastFrameTimeRef.current = currentTime;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Use hardware acceleration with willReadFrequently: false
            ctx.filter = "blur(12px)"; // Further reduced blur for better performance

            const totalBeams = beamsRef.current.length;
            beamsRef.current.forEach((beam, index) => {
                beam.y -= beam.speed;
                beam.pulse += beam.pulseSpeed;

                // Reset beam when it goes off screen
                if (beam.y + beam.length < -100) {
                    resetBeam(beam, index, totalBeams);
                }

                drawBeam(ctx, beam);
            });

            animationFrameRef.current = requestAnimationFrame(animate);
        }

        animate(performance.now());

        return () => {
            window.removeEventListener("resize", updateCanvasSize);
            if (animationFrameRef.current) {
                cancelAnimationFrame(animationFrameRef.current);
            }
        };
    }, [intensity]);

    return (
        <div
            className={cn(
                "relative min-h-screen w-full overflow-hidden bg-neutral-950",
                className
            )}
        >
            <canvas
                ref={canvasRef}
                className="absolute inset-0"
                style={{ 
                    filter: "blur(8px)",
                    transform: "translateZ(0)", // Force hardware acceleration
                    willChange: "transform"
                }}
            />

            <motion.div
                className="absolute inset-0 bg-neutral-950/8"
                animate={{
                    opacity: [0.04, 0.12, 0.04],
                }}
                transition={{
                    duration: 12,
                    ease: "easeInOut",
                    repeat: Number.POSITIVE_INFINITY,
                }}
                style={{
                    backdropFilter: "blur(30px)",
                    transform: "translateZ(0)", // Force hardware acceleration
                }}
            />

            <div className="relative z-10 w-full min-h-screen">
                {children}
            </div>
        </div>
    );
}
