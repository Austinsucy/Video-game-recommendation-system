export type FeatureStatus = 'planned' | 'partial' | 'available';

/** Chip text for a feature's status, shared by the feature panels and the guided tour. */
export const STATUS_LABEL: Record<FeatureStatus, string> = {
  planned: 'Not available yet',
  partial: 'Partly available',
  available: 'Available',
};
