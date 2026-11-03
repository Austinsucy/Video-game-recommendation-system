import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import { FitIcon, MinusIcon, PlusIcon } from '../icons';

interface MapControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export default function MapControls({ onZoomIn, onZoomOut, onReset }: MapControlsProps) {
  const controls = [
    { label: 'Zoom in', onClick: onZoomIn, Icon: PlusIcon },
    { label: 'Zoom out', onClick: onZoomOut, Icon: MinusIcon },
    { label: 'Reset view', onClick: onReset, Icon: FitIcon },
  ];
  return (
    <div className="map-controls" role="group" aria-label="Map view">
      {controls.map(({ label, onClick, Icon }) => (
        <Tooltip key={label} title={label} placement="left">
          <IconButton size="small" aria-label={label} onClick={onClick}>
            <Icon fontSize="small" />
          </IconButton>
        </Tooltip>
      ))}
    </div>
  );
}
