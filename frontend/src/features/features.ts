import type { SvgIconProps } from '@mui/material/SvgIcon';
import type { ComponentType } from 'react';
import {
  GenresIcon, HelpIcon, LegendIcon, LibraryIcon, RecommendIcon, ScanIcon, ShareIcon,
} from '../components/icons';

export type FeatureId = 'recommendations' | 'genres' | 'legend' | 'scan' | 'share' | 'steam' | 'help';

export interface FeatureEntry {
  id: FeatureId;
  label: string;
  Icon: ComponentType<SvgIconProps>;
}

// Toolbar order, left to right. Help sits on the far right after search.
// Each entry opens the panel of the same id in FeaturePanelHost.
export const TOOLBAR_FEATURES: FeatureEntry[] = [
  { id: 'recommendations', label: 'Recommendations', Icon: RecommendIcon },
  { id: 'genres', label: 'Genres', Icon: GenresIcon },
  { id: 'legend', label: 'Legend', Icon: LegendIcon },
  { id: 'scan', label: 'Scan', Icon: ScanIcon },
  { id: 'share', label: 'Save / Share', Icon: ShareIcon },
  { id: 'steam', label: 'Steam Library', Icon: LibraryIcon },
];

export const HELP_FEATURE: FeatureEntry = { id: 'help', label: 'Help', Icon: HelpIcon };

/** DOM id of a feature's toolbar button, used to return focus when its panel closes. */
export function featureButtonId(id: FeatureId) {
  return `feature-button-${id}`;
}
