'use client';

import { useRouter } from 'next/navigation';
import { AnimatedAIChat } from './components/ui/animated-ai-chat';

export default function HomePage() {
  const router = useRouter();

  return <AnimatedAIChat onSendMessage={() => router.push('/main-chat')} />;
}
