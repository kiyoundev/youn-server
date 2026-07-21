import { GitBranch } from "lucide-react";
import { GitStatusDots } from "@/components/ui/git-status-dots";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface GitUpdateTileProps {
  name: string;
  commitsBehind: number;
  onUpdate?: () => void;
  className?: string;
}

const GitUpdateTile = ({
  name,
  commitsBehind,
  onUpdate,
  className,
}: GitUpdateTileProps) => {
  const isUpToDate = commitsBehind === 0;

  return (
    <Card className={className ?? "w-[176px] h-[191.5px]"}>
      <CardContent className="flex flex-col gap-4 h-full">
        <GitBranch className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex flex-col gap-1">
          <Label className="text-[22px] font-normal block">
            {name}
          </Label>
          <Label className="text-[14px] font-normal text-brand-300">
            {isUpToDate ? "Up to Date" : `${commitsBehind} Commits Behind`}
          </Label>
        </div>
        <GitStatusDots commitsBehind={commitsBehind} />
        {!isUpToDate && (
          <Button
            onClick={onUpdate}
            variant="pill"
            className="w-full h-auto py-2 text-[14px] font-normal mt-auto"
          >
            Update
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default GitUpdateTile;
