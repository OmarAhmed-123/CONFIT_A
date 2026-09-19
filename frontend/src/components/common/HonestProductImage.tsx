import React from "react";

interface HonestProductImageProps extends Omit<
  React.ImgHTMLAttributes<HTMLImageElement>,
  "src" | "alt" | "onError"
> {
  src?: string | null;
  alt: string;
  unavailableLabel?: string;
}

/**
 * Product images must never fall back to a fake product photo. If the real
 * catalog image fails, show an explicit non-product placeholder instead.
 */
export const HonestProductImage: React.FC<HonestProductImageProps> = ({
  src,
  alt,
  className = "",
  unavailableLabel = "Image unavailable",
  ...props
}) => {
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) {
    return (
      <div
        className={`flex h-full w-full items-center justify-center bg-slate-100 text-center text-[11px] font-semibold text-slate-500 ${className}`}
        role="img"
        aria-label={`${alt} — ${unavailableLabel}`}
      >
        <span className="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 shadow-2xs">
          {unavailableLabel}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      onError={() => setFailed(true)}
      {...props}
    />
  );
};
