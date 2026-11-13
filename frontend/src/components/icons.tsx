import SvgIcon, { type SvgIconProps } from '@mui/material/SvgIcon';
import type { ReactNode } from 'react';

// Simple line icons drawn on a 24 x 24 grid. They avoid adding an icon
// package; swap in @mui/icons-material later if the team prefers.
function lineIcon(paths: ReactNode) {
  return function LineIcon(props: SvgIconProps) {
    return (
      <SvgIcon
        {...props}
        viewBox="0 0 24 24"
        sx={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', ...props.sx }}
      >
        {paths}
      </SvgIcon>
    );
  };
}

export const SearchIcon = lineIcon(<><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5 5" /></>);
export const RecommendIcon = lineIcon(
  <><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></>,
);
export const GenresIcon = lineIcon(<path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" />);
export const LegendIcon = lineIcon(
  <><circle cx="6" cy="7" r="1.6" /><circle cx="6" cy="12" r="1.6" /><circle cx="6" cy="17" r="1.6" /><path d="M10.5 7H20M10.5 12H20M10.5 17H20" /></>,
);
export const ScanIcon = lineIcon(
  <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.5" /><path d="M12 12l5.5-5.5" /></>,
);
export const ShareIcon = lineIcon(
  <><circle cx="17" cy="6" r="2.5" /><circle cx="7" cy="12" r="2.5" /><circle cx="17" cy="18" r="2.5" /><path d="M9.2 10.8l5.6-3.4M9.2 13.2l5.6 3.4" /></>,
);
export const LibraryIcon = lineIcon(
  <><rect x="4" y="5" width="4" height="14" rx="1" /><rect x="10" y="5" width="4" height="14" rx="1" /><path d="M16.5 6.2l3.6 12.3" /></>,
);
export const HelpIcon = lineIcon(
  <><circle cx="12" cy="12" r="8.5" /><path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.5" /><path d="M12 16.8v.2" /></>,
);
export const CloseIcon = lineIcon(<path d="M6 6l12 12M18 6L6 18" />);
export const PlusIcon = lineIcon(<path d="M12 5v14M5 12h14" />);
export const MinusIcon = lineIcon(<path d="M5 12h14" />);
export const FitIcon = lineIcon(
  <path d="M4 9V5h4M16 5h4v4M20 15v4h-4M8 19H4v-4" />,
);
export const SunIcon = lineIcon(
  <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" /></>,
);
export const MoonIcon = lineIcon(<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z" />);
