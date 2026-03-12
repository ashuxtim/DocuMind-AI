import { motion } from 'framer-motion';
import { FileText, Network, GitFork, Activity, Brain, Cpu } from 'lucide-react';
import { Card, CardContent } from '@/ui/card';
import { cn } from '@/lib/utils';

function StatCard({ icon: Icon, label, value, accent }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
        >
            <Card className="relative overflow-hidden group hover:border-primary/30 transition-smooth">
                <div
                    className={cn(
                        'absolute top-0 left-0 right-0 h-[2px]',
                        accent || 'bg-gradient-to-r from-primary to-secondary'
                    )}
                />
                <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                        <div className="space-y-2">
                            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                {label}
                            </p>
                            <p className="text-2xl font-bold text-foreground tracking-tight">
                                {value}
                            </p>
                        </div>
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-smooth">
                            <Icon className="w-5 h-5 text-primary" />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
}

export function OverviewCards({ overview }) {
    if (!overview) return null;

    return (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            <StatCard icon={FileText} label="Documents" value={overview.total_documents} />
            <StatCard icon={Network} label="Entities" value={overview.total_entities} />
            <StatCard icon={GitFork} label="Relations" value={overview.total_relations} />
            <StatCard
                icon={Activity}
                label="Active Jobs"
                value={overview.active_jobs}
                accent={overview.active_jobs > 0 ? 'bg-gradient-to-r from-amber-500 to-orange-500' : undefined}
            />
            <StatCard icon={Brain} label="LLM Provider" value={overview.llm_provider} />
            <StatCard icon={Cpu} label="Concurrency" value={overview.concurrency_mode} />
        </div>
    );
}
