import { motion } from 'framer-motion';
import { Network } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/ui/card';
import { Badge } from '@/ui/badge';
import { Separator } from '@/ui/separator';

function MiniBar({ value, max, color = 'bg-primary' }) {
    const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
    return (
        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <motion.div
                className={`h-full rounded-full ${color}`}
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
            />
        </div>
    );
}

export function GraphPanel({ graph }) {
    if (!graph) return null;

    const topEntities = (graph.top_entities || []).slice(0, 6);
    const maxConnections = topEntities.length > 0 ? topEntities[0].connections : 1;

    const relationEntries = Object.entries(graph.relation_types || {})
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5);
    const maxRelCount = relationEntries.length > 0 ? relationEntries[0][1] : 1;

    return (
        <Card className="h-full">
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Network className="w-4 h-4 text-secondary" />
                    Graph Intelligence
                </CardTitle>
            </CardHeader>
            <CardContent>
                {/* Summary stats row */}
                <div className="flex items-center gap-4 mb-5">
                    <div className="flex-1 text-center p-3 rounded-lg bg-muted/50">
                        <p className="text-lg font-bold text-foreground">{graph.total_nodes}</p>
                        <p className="text-xs text-muted-foreground">Nodes</p>
                    </div>
                    <div className="flex-1 text-center p-3 rounded-lg bg-muted/50">
                        <p className="text-lg font-bold text-foreground">{graph.total_links}</p>
                        <p className="text-xs text-muted-foreground">Edges</p>
                    </div>
                    <div className="flex-1 text-center p-3 rounded-lg bg-muted/50">
                        <p className="text-lg font-bold text-foreground">{relationEntries.length}</p>
                        <p className="text-xs text-muted-foreground">Rel Types</p>
                    </div>
                </div>

                <Separator className="mb-4" />

                {/* Top Entities */}
                {topEntities.length > 0 ? (
                    <>
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                            Most Connected Entities
                        </h4>
                        <div className="space-y-3">
                            {topEntities.map((entity, idx) => (
                                <div key={entity.name || idx} className="space-y-1">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-foreground font-medium truncate max-w-[200px]">
                                            {entity.name}
                                        </span>
                                        <Badge variant="outline" className="text-xs ml-2 flex-shrink-0">
                                            {entity.connections}
                                        </Badge>
                                    </div>
                                    <MiniBar
                                        value={entity.connections}
                                        max={maxConnections}
                                        color={
                                            idx === 0
                                                ? 'bg-gradient-to-r from-primary to-emerald-400'
                                                : idx === 1
                                                    ? 'bg-gradient-to-r from-secondary to-purple-400'
                                                    : 'bg-primary/60'
                                        }
                                    />
                                </div>
                            ))}
                        </div>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center py-6 text-center">
                        <Network className="w-8 h-8 text-muted-foreground/40 mb-2" />
                        <p className="text-sm text-muted-foreground">No graph data yet</p>
                    </div>
                )}

                {/* Relation Type Distribution */}
                {relationEntries.length > 0 && (
                    <>
                        <Separator className="my-4" />
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                            Relation Distribution
                        </h4>
                        <div className="space-y-2">
                            {relationEntries.map(([type, count]) => (
                                <div key={type} className="flex items-center justify-between text-xs">
                                    <span className="text-muted-foreground font-mono truncate max-w-[160px]">
                                        {type}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        <div className="w-16">
                                            <MiniBar value={count} max={maxRelCount} color="bg-secondary/70" />
                                        </div>
                                        <span className="text-foreground font-medium w-6 text-right">{count}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}
