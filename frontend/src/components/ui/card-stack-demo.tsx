"use client";

import { CardStack, type CardStackItem } from "@/components/ui/card-stack";

const items: CardStackItem[] = [
  {
    id: 1,
    title: "Executive Tailoring",
    description: "Structured suiting for confident workdays and formal appointments.",
    imageSrc: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80",
    href: "/discover",
  },
  {
    id: 2,
    title: "Evening Elegance",
    description: "Silk textures and refined lines for premium occasion dressing.",
    imageSrc: "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80",
    href: "/discover",
  },
  {
    id: 3,
    title: "Minimal Capsule",
    description: "Modern classics built for repeat wear and effortless pairing.",
    imageSrc: "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80",
    href: "/discover",
  },
  {
    id: 4,
    title: "Street Utility",
    description: "Casual layers with practical silhouettes and sharp proportions.",
    imageSrc: "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80",
    href: "/discover",
  },
  {
    id: 5,
    title: "Resort Linen",
    description: "Lightweight summer styling for travel, brunch, and warm evenings.",
    imageSrc: "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80",
    href: "/discover",
  },
];

export default function CardStackDemoPage() {
  return (
    <div className="w-full">
      <div className="mx-auto w-full max-w-5xl p-8">
        <CardStack
          items={items}
          initialIndex={0}
          autoAdvance
          intervalMs={2000}
          pauseOnHover
          showDots
        />
      </div>
    </div>
  );
}
