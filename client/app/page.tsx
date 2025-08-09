/* eslint-disable */
'use client';

import { useRouter } from 'next/navigation';
import { AnimatedAIChat } from './components/ui/animated-ai-chat';
import { AuroraBackground } from '../components/ui/aurora-background';

export default function HomePage() {
  const router = useRouter();

  const handleSendMessage = (_message: string) => {
    router.push('/main-chat');
  };

  return (
    <AuroraBackground>
      <AnimatedAIChat onSendMessage={handleSendMessage} />
    </AuroraBackground>
  );
}