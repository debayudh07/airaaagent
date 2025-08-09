
/* eslint-disable */
"use client";

import { useState } from "react";
import { SendIcon } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import * as React from "react"
import { TypingAnimation } from "../../../components/magicui/typing-animation";
import { AuroraText } from "@/components/magicui/aurora-text";

interface CommandSuggestion {
    icon: React.ReactNode;
    label: string;
    description: string;
    prefix: string;
}

interface AnimatedAIChatProps {
    onSendMessage?: (message: string) => void;
}

export function AnimatedAIChat({ onSendMessage }: AnimatedAIChatProps) {
    const [isTyping, setIsTyping] = useState(false);

    const commandSuggestions: CommandSuggestion[] = [];


    

    return (
        <div className="min-h-screen flex flex-col w-full items-center justify-center bg-transparent text-white p-6 relative overflow-hidden">
        <div className="absolute inset-0 w-full h-full overflow-hidden">
                <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/3 rounded-full mix-blend-normal filter blur-[140px] animate-pulse" />
                <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-500/3 rounded-full mix-blend-normal filter blur-[140px] animate-pulse delay-1000" />
                <div className="absolute top-1/4 right-1/3 w-64 h-64 bg-fuchsia-500/2 rounded-full mix-blend-normal filter blur-[120px] animate-pulse delay-2000" />
            </div>
            <div className="w-full max-w-2xl mx-auto relative">
                <motion.div 
                    className="relative z-10 space-y-12"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                >
                    <div className="text-center space-y-6">
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2, duration: 0.5 }}
                            className="inline-block"
                        >
                            <h1 className="text-6xl sm:text-7xl md:text-8xl font-extrabold tracking-wide bg-clip-text text-transparent bg-gradient-to-r from-white/95 to-white/70 pb-2">
                                <AuroraText>Welcome to Aira</AuroraText>
                            </h1>
                            <motion.div 
                                className="h-[1px] bg-gradient-to-r from-transparent via-white/15 to-transparent"
                                initial={{ width: 0, opacity: 0 }}
                                animate={{ width: "100%", opacity: 1 }}
                                transition={{ delay: 0.5, duration: 0.8 }}
                            />
                        </motion.div>
                        <TypingAnimation
                            className="text-3xl sm:text-4xl text-white/80 font-semibold tracking-wide"
                            duration={80}
                            delay={1000}
                        >
                            Your intelligent assistant
                        </TypingAnimation>
                    </div>

                    <motion.div 
                        className="flex justify-center"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.3, duration: 0.6 }}
                    >
                        <motion.button
                            type="button"
                            onClick={() => {
                                if (onSendMessage) {
                                    onSendMessage("Start chat");
                                }
                            }}
                            whileHover={{ scale: 1.05, y: -2 }}
                            whileTap={{ scale: 0.95 }}
                            className="px-8 py-4 bg-white text-black rounded-2xl text-lg font-medium shadow-xl hover:shadow-2xl transition-all duration-300 flex items-center gap-3 group"
                            style={{
                                background: 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)',
                                boxShadow: '0 20px 40px -12px rgba(255, 255, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.8)'
                            }}
                        >
                            <span>Chat with Aira</span>
                            <motion.div
                                className="group-hover:translate-x-1 transition-transform duration-200"
                            >
                                <SendIcon className="w-5 h-5" />
                            </motion.div>
                        </motion.button>
                    </motion.div>

                    {/* Suggestive buttons removed as requested */}
                </motion.div>
            </div>

            <AnimatePresence>
                {isTyping && (
                    <motion.div 
                        className="fixed bottom-8 mx-auto transform -translate-x-1/2 backdrop-blur-2xl bg-white/[0.08] rounded-full px-4 py-2 shadow-xl border border-white/[0.15]"
                        style={{
                            boxShadow: '0 15px 35px -5px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
                        }}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 20 }}
                    >
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-7 rounded-full bg-white/[0.08] flex items-center justify-center text-center">
                                <span className="text-xs font-light text-white/90 mb-0.5">aira</span>
                            </div>
                            <div className="flex items-center gap-2 text-sm text-white/80">
                                <span className="font-light">Processing</span>
                                <TypingDots />
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>


        </div>
    );
}

function TypingDots() {
    return (
        <div className="flex items-center ml-1">
            {[1, 2, 3].map((dot) => (
                <motion.div
                    key={dot}
                    className="w-1.5 h-1.5 bg-white/90 rounded-full mx-0.5"
                    initial={{ opacity: 0.3 }}
                    animate={{ 
                        opacity: [0.3, 0.9, 0.3],
                        scale: [0.85, 1.1, 0.85]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: dot * 0.15,
                        ease: "easeInOut",
                    }}
                    style={{
                        boxShadow: "0 0 4px rgba(255, 255, 255, 0.3)"
                    }}
                />
            ))}
        </div>
    );
}

interface ActionButtonProps {
    icon: React.ReactNode;
    label: string;
}

function ActionButton({ icon, label }: ActionButtonProps) {
    const [isHovered, setIsHovered] = useState(false);
    
    return (
        <motion.button
            type="button"
            whileHover={{ scale: 1.05, y: -2 }}
            whileTap={{ scale: 0.97 }}
            onHoverStart={() => setIsHovered(true)}
            onHoverEnd={() => setIsHovered(false)}
            className="flex items-center gap-2 px-4 py-2 bg-neutral-900 hover:bg-neutral-800 rounded-full border border-neutral-800 text-neutral-400 hover:text-white transition-all relative overflow-hidden group"
        >
            <div className="relative z-10 flex items-center gap-2">
                {icon}
                <span className="text-xs relative z-10">{label}</span>
            </div>
            
            <AnimatePresence>
                {isHovered && (
                    <motion.div 
                        className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-indigo-500/10"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                    />
                )}
            </AnimatePresence>
            
            <motion.span 
                className="absolute bottom-0 left-0 w-full h-0.5 bg-gradient-to-r from-violet-500 to-indigo-500"
                initial={{ width: 0 }}
                whileHover={{ width: "100%" }}
                transition={{ duration: 0.3 }}
            />
        </motion.button>
    );
}

const rippleKeyframes = `
@keyframes ripple {
  0% { transform: scale(0.5); opacity: 0.6; }
  100% { transform: scale(2); opacity: 0; }
}
`;

if (typeof document !== 'undefined') {
    const style = document.createElement('style');
    style.innerHTML = rippleKeyframes;
    document.head.appendChild(style);
}


