import { Upload, MessageSquare, Eye, TrendingUp, ArrowRight, Zap } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/ui/card';

const actions = [
    {
        id: 'docs',
        label: 'Upload',
        description: 'Add documents',
        icon: Upload,
        iconBg: 'bg-primary/10 group-hover:bg-primary/20',
        iconColor: 'text-primary',
        hoverBorder: 'hover:border-primary/30',
    },
    {
        id: 'chat',
        label: 'Query',
        description: 'Ask questions',
        icon: MessageSquare,
        iconBg: 'bg-secondary/10 group-hover:bg-secondary/20',
        iconColor: 'text-secondary',
        hoverBorder: 'hover:border-secondary/30',
    },
    {
        id: 'graph',
        label: 'Graph',
        description: 'Explore entities',
        icon: Eye,
        iconBg: 'bg-emerald-500/10 group-hover:bg-emerald-500/20',
        iconColor: 'text-emerald-500',
        hoverBorder: 'hover:border-primary/30',
    },
    {
        id: 'summary',
        label: 'Summary',
        description: 'Document briefs',
        icon: TrendingUp,
        iconBg: 'bg-amber-500/10 group-hover:bg-amber-500/20',
        iconColor: 'text-amber-500',
        hoverBorder: 'hover:border-amber-500/30',
    },
];

export function QuickActions({ onViewChange }) {
    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    Quick Actions
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-2 gap-3">
                    {actions.map((action) => {
                        const Icon = action.icon;
                        return (
                            <button
                                key={action.id}
                                onClick={() => onViewChange?.(action.id)}
                                className={`flex items-center gap-3 p-4 rounded-lg border border-border bg-card hover:bg-muted/50 ${action.hoverBorder} transition-smooth group text-left`}
                            >
                                <div className={`w-10 h-10 rounded-lg ${action.iconBg} flex items-center justify-center transition-smooth`}>
                                    <Icon className={`w-5 h-5 ${action.iconColor}`} />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-foreground">{action.label}</p>
                                    <p className="text-xs text-muted-foreground">{action.description}</p>
                                </div>
                                <ArrowRight className="w-4 h-4 text-muted-foreground ml-auto opacity-0 group-hover:opacity-100 transition-smooth" />
                            </button>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}
