import { motion } from 'framer-motion';
import { FileText, Upload, CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/ui/card';
import { Badge } from '@/ui/badge';

function StatusBadge({ status }) {
    switch (status) {
        case 'completed':
            return (
                <Badge variant="success" className="text-xs gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Ready
                </Badge>
            );
        case 'processing':
            return (
                <Badge variant="processing" className="text-xs gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Processing
                </Badge>
            );
        case 'failed':
            return (
                <Badge variant="destructive" className="text-xs gap-1">
                    <XCircle className="w-3 h-3" /> Failed
                </Badge>
            );
        default:
            return (
                <Badge variant="outline" className="text-xs gap-1">
                    <AlertCircle className="w-3 h-3" /> {status || 'Unknown'}
                </Badge>
            );
    }
}

export function IngestionPanel({ documents = [] }) {
    const processingDocs = documents.filter((d) => d.status === 'processing');
    const recentDocs = documents.slice(0, 8);

    return (
        <Card className="h-full">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Upload className="w-4 h-4 text-primary" />
                        Ingestion Activity
                    </CardTitle>
                    {processingDocs.length > 0 && (
                        <Badge variant="processing" className="text-xs">
                            {processingDocs.length} active
                        </Badge>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {recentDocs.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                        <FileText className="w-10 h-10 text-muted-foreground/40 mb-3" />
                        <p className="text-sm text-muted-foreground">No documents ingested yet</p>
                        <p className="text-xs text-muted-foreground/70 mt-1">
                            Upload documents to see activity here
                        </p>
                    </div>
                ) : (
                    <div className="space-y-2">
                        {recentDocs.map((doc, idx) => (
                            <motion.div
                                key={doc.filename || idx}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: idx * 0.04 }}
                                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50 transition-smooth group"
                            >
                                <div className="flex items-center gap-3 min-w-0 flex-1">
                                    <div className="w-8 h-8 rounded bg-muted flex items-center justify-center flex-shrink-0">
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium text-foreground truncate">
                                            {doc.filename}
                                        </p>
                                        {doc.uploaded_at && (
                                            <p className="text-xs text-muted-foreground">
                                                {new Date(doc.uploaded_at).toLocaleDateString(undefined, {
                                                    month: 'short',
                                                    day: 'numeric',
                                                    hour: '2-digit',
                                                    minute: '2-digit',
                                                })}
                                            </p>
                                        )}
                                    </div>
                                </div>
                                <StatusBadge status={doc.status} />
                            </motion.div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
