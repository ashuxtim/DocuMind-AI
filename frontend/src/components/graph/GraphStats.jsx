import { motion } from 'framer-motion';
import { Card } from '@/ui/card';
import { Badge } from '@/ui/badge';

export function GraphStats({ stats }) {
  if (!stats) return null;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="absolute top-4 right-4 z-10 pointer-events-none"
    >
      <Card className="p-4 w-64 pointer-events-auto">
        <h3 className="text-sm font-semibold text-foreground mb-3">
          Graph Statistics
        </h3>
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Total Entities</span>
            <Badge variant="outline">{stats.totalNodes || 0}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Relationships</span>
            <Badge variant="outline">{stats.totalLinks || 0}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Documents</span>
            <Badge variant="outline">{stats.totalDocs || 0}</Badge>
          </div>
        </div>

        {stats.topEntities && stats.topEntities.length > 0 && (
          <>
            <div className="h-px bg-border my-3" />
            <h4 className="text-xs font-medium text-foreground mb-2">
              Top Entities
            </h4>
            <div className="space-y-1">
              {stats.topEntities.slice(0, 5).map((entity, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground truncate max-w-[150px]">
                    {entity.name}
                  </span>
                  <Badge variant="secondary" className="text-xs">
                    {entity.connections}
                  </Badge>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>
    </motion.div>
  );
}
