import React from 'react';
import { CircularGallery, type GalleryItem } from '@/components/ui/circular-gallery';

const galleryData: GalleryItem[] = [
  {
    common: 'Tailored power suit',
    binomial: 'CONFIT editorial workwear',
    photo: {
      url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80',
      text: 'person wearing a tailored suit in an editorial setting',
      pos: '50% 35%',
      by: 'Unsplash',
    },
  },
  {
    common: 'Champagne evening gown',
    binomial: 'occasion-ready luxury styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80',
      text: 'champagne evening dress on a model',
      pos: '50% 30%',
      by: 'Tamara Bellis',
    },
  },
  {
    common: 'Minimal capsule layers',
    binomial: 'modern essentials styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80',
      text: 'minimal wardrobe layers on a model',
      pos: '50% 40%',
      by: 'Hunters Race',
    },
  },
  {
    common: 'Streetwear utility edit',
    binomial: 'casual smart outfit formula',
    photo: {
      url: 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80',
      text: 'fashion model wearing casual streetwear',
      pos: '50% 28%',
      by: 'Apostolos Vamvouras',
    },
  },
  {
    common: 'Runway black statement',
    binomial: 'premium monochrome styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?w=900&auto=format&fit=crop&q=80',
      text: 'woman in black fashion outfit posing outdoors',
      pos: '50% 20%',
      by: 'Laura Chouette',
    },
  },
  {
    common: 'Soft neutral tailoring',
    binomial: 'quiet luxury daywear',
    photo: {
      url: 'https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=900&auto=format&fit=crop&q=80',
      text: 'neutral fashion outfit in soft daylight',
      pos: '50% 35%',
      by: 'Brooke Cagle',
    },
  },
  {
    common: 'Weekend denim uniform',
    binomial: 'wardrobe foundation look',
    photo: {
      url: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=900&auto=format&fit=crop&q=80',
      text: 'fashion portrait with denim styling',
      pos: '50% 30%',
      by: 'Tamara Bellis',
    },
  },
  {
    common: 'Resort linen palette',
    binomial: 'warm-weather capsule styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80',
      text: 'editorial model in resort-inspired fashion',
      pos: '50% 30%',
      by: 'Clem Onojeghuo',
    },
  },
];

const CircularGalleryDemo = () => {
  return (
    <div className="w-full bg-background text-foreground" style={{ height: '500vh' }}>
      <div className="sticky top-0 flex h-screen w-full flex-col items-center justify-center overflow-hidden">
        <div className="absolute top-16 z-10 mb-8 text-center">
          <h1 className="font-serif text-4xl font-bold text-[#1B1F3B]">CONFIT Editorial Gallery</h1>
          <p className="text-muted-foreground">Scroll to rotate the lookbook</p>
        </div>
        <div className="h-full w-full">
          <CircularGallery items={galleryData} />
        </div>
      </div>
    </div>
  );
};

export default CircularGalleryDemo;
