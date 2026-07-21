import { Zap } from "lucide-react";
import ServiceTile from "@/components/tiles/service-tile";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface ServicesTileProps {
  plexHealthy?: boolean;
  className?: string;
}

const ServicesTile = ({ plexHealthy = true, className }: ServicesTileProps) => {
  return (
    <Card className={className ?? "w-full gap-4"}>
      <CardHeader>
        <CardTitle className="font-ndot">Services</CardTitle>
      </CardHeader>
      <CardContent className="flex justify-between gap-5 w-full">
        <ServiceTile
          icon={Zap}
          name="Watchlist Notifier"
          status="Polling"
          healthStatus="healthy"
          details={["Last check 30min ago", "Next check in 30min"]}
        />
        <ServiceTile
          icon={Zap}
          name="Stock Price Alert"
          status="Live (WS)"
          healthStatus="healthy"
          details={["Last message 3s ago", "Fallback interval 60s"]}
        />
        <ServiceTile
          icon={Zap}
          name="TradingAgents"
          status="Idle"
          healthStatus="healthy"
          details={["Trigger: Manual", "Last run 1h ago — success"]}
        />
        <ServiceTile
          icon={Zap}
          name="Plex"
          status={plexHealthy ? "Healthy" : "Unhealthy"}
          healthStatus={plexHealthy ? "healthy" : "down"}
          details={["Port 32400"]}
        />
      </CardContent>
    </Card>
  );
};

export default ServicesTile;
