// Small line icons drawn for this workspace (1.6px strokes, 20px box).
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Base({ children, ...props }: IconProps) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const LeafMark = (props: IconProps) => (
  <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true" {...props}>
    <path d="M6 22c0-9 6-15 16-16-1 10-7 16-16 16Z" fill="#a7bd8a" />
    <path d="M6 22 17 11" stroke="#1f3d2e" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

export const IconSprout = (props: IconProps) => (
  <Base {...props}>
    <path d="M10 17V9" />
    <path d="M10 10c0-3.5-2.5-5.5-6-5.5 0 3.5 2.5 5.5 6 5.5Z" />
    <path d="M10 12c0-3 2-5 5.5-5 0 3-2 5-5.5 5Z" />
    <path d="M6 17h8" />
  </Base>
);

export const IconFlag = (props: IconProps) => (
  <Base {...props}>
    <path d="M5 17V3.5" />
    <path d="M5 4h9l-2 3.25L14 10.5H5" />
  </Base>
);

export const IconLens = (props: IconProps) => (
  <Base {...props}>
    <circle cx="8.5" cy="8.5" r="5" />
    <path d="m12.5 12.5 4 4" />
    <path d="M6.5 10c0-2 1-3.2 3.5-3.5 0 2-1.2 3.5-3.5 3.5Z" />
  </Base>
);

export const IconBook = (props: IconProps) => (
  <Base {...props}>
    <path d="M4 4.5c2-.8 4-.6 6 .8v11c-2-1.4-4-1.6-6-.8v-11Z" />
    <path d="M16 4.5c-2-.8-4-.6-6 .8v11c2-1.4 4-1.6 6-.8v-11Z" />
  </Base>
);

export const IconPeople = (props: IconProps) => (
  <Base {...props}>
    <circle cx="7.5" cy="7" r="2.75" />
    <path d="M2.75 16c.6-2.8 2.4-4.25 4.75-4.25S11.65 13.2 12.25 16" />
    <path d="M13 4.6a2.6 2.6 0 0 1 0 4.8" />
    <path d="M14.5 11.9c1.4.5 2.4 1.8 2.75 4.1" />
  </Base>
);

export const IconMegaphone = (props: IconProps) => (
  <Base {...props}>
    <path d="M3.5 8v4h2.5l6 3.5v-11L6 8H3.5Z" />
    <path d="M6.5 12.2 7.5 16.5" />
    <path d="M15 8a3 3 0 0 1 0 4" />
  </Base>
);

export const IconClose = (props: IconProps) => (
  <Base {...props}>
    <path d="m5 5 10 10M15 5 5 15" />
  </Base>
);

export const IconMenu = (props: IconProps) => (
  <Base {...props}>
    <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
  </Base>
);

export const IconPlus = (props: IconProps) => (
  <Base {...props}>
    <path d="M10 4.5v11M4.5 10h11" />
  </Base>
);
