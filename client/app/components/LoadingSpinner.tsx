/* eslint-disable */
'use client';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
}

export default function LoadingSpinner({ size = 'md', text = 'Loading...' }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-6 h-6 border-2',
    lg: 'w-8 h-8 border-3'
  };

  const textSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base'
  };

  return (
    <div className="flex items-center justify-center space-x-3">
      {/* Simple white spinner */}
      <div 
        className={`${sizeClasses[size]} border-white/20 border-t-white rounded-full animate-spin`}
        style={{ animationDuration: '1s' }}
      />
      
      {text && (
        <span className={`text-white/70 font-medium ${textSizes[size]}`}>
          {text}
        </span>
      )}
    </div>
  );
}