import { Container } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusDot, type ServiceStatus } from "@/components/ui/status-dot";

type ContainerStatus = "running" | "exited" | "restarting";

const STATUS_LABEL: Record<ContainerStatus, string> = {
  running: "Healthy",
  exited: "Unhealthy",
  restarting: "Restarting",
};

const STATUS_HEALTH: Record<ContainerStatus, ServiceStatus> = {
  running: "healthy",
  exited: "down",
  restarting: "degraded",
};

interface DockerTileProps {
  name: string;
  status: ContainerStatus;
  port: number;
  onRestart?: () => void;
  className?: string;
}

const DockerTile = ({
  name,
  status,
  port,
  onRestart,
  className,
}: DockerTileProps) => {
  return (
    <Card className={className ?? "w-[176px] h-[191.5px]"}>
      <CardContent className="flex flex-col gap-4 h-full">
        <Container className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex flex-col gap-2">
          <Label className="text-[22px] font-normal block">
            {name}
          </Label>
          <div className="flex items-center gap-2">
            <Label className="text-[14px] font-normal text-brand-300 block">
              {STATUS_LABEL[status]}
            </Label>
            <StatusDot status={STATUS_HEALTH[status]} />
          </div>
        </div>
        <div className="flex flex-col">
          <Label className="text-[12px] font-normal text-brand-300">
            Port {port}
          </Label>
        </div>
        <Button
          onClick={onRestart}
          variant="pill"
          className="w-full h-auto py-2 text-[14px] font-normal mt-auto"
        >
          Restart
        </Button>
      </CardContent>
    </Card>
  );
};

export default DockerTile;
