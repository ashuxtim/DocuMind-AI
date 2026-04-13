import { useWorkspace } from '@/contexts/WorkspaceContext';
import DocumentGrid from '@/components/workspace/DocumentGrid';
import DocView from '@/components/workspace/DocView';

export function WorkspacePage() {
  const { activeDoc } = useWorkspace();
  return activeDoc ? <DocView /> : <DocumentGrid />;
}
