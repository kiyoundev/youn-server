import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SystemRestartTileProps {
  onRestart?: () => void;
  className?: string;
}

const SystemRestartTile = ({
  onRestart,
  className,
}: SystemRestartTileProps) => {
  return (
    <Button
      onClick={onRestart}
      variant="pill"
      className={cn(
        "flex-col h-auto gap-2",
        className ?? "w-[176px] h-[176px]",
      )}
    >
      <RotateCw size={24} strokeWidth={1.25} />
      <span className="text-[18px] font-normal">System Restart</span>
    </Button>
  );
};

export default SystemRestartTile;
