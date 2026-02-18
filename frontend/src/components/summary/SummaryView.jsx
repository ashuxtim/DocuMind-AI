import { motion } from 'framer-motion';
import { SummaryCard } from './SummaryCard';
import { EmptyState } from '@/components/shared/EmptyState';
import { Sparkles } from 'lucide-react';

export function SummaryView({ documents, onViewDocument }) {
  // Filter documents that have summaries
  const documentsWithSummaries = documents.filter(doc => doc.summary);

  if (documentsWithSummaries.length === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No summaries yet"
        description="Generate summaries from the Documents page or Chat to see them here"
      />
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-6"
    >
      {documentsWithSummaries.map((doc, index) => (
        <motion.div
          key={doc.filename}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.05 }}
        >
          <SummaryCard
            filename={doc.filename}
            summary={doc.summary}
            createdAt={doc.completed_at}
            fileType={doc.type}
            onViewDocument={onViewDocument}
          />
        </motion.div>
      ))}
    </motion.div>
  );
}
