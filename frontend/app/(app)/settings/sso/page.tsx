'use client';

import { ShieldCheck } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';

import { AlertError, AlertSuccess } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, type DialogHandle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCurrentUser } from '@/lib/hooks/use-auth';
import {
  useDeleteSsoConfig,
  useSsoConfig,
  useUpsertSsoConfig,
} from '@/lib/hooks/use-sso';

export default function SsoSettingsPage(): React.JSX.Element {
  const currentUser = useCurrentUser();
  const role = currentUser.data?.role;
  const isOrgAdmin = role === 'org-admin' || role === 'superadmin';

  if (currentUser.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary"
          role="status"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (!isOrgAdmin) {
    return (
      <Card>
        <CardHeader>
          <CardTitle as="h1">SSO settings</CardTitle>
        </CardHeader>
        <CardContent>
          <AlertError>
            Only an organization admin can view or manage SSO configuration.
          </AlertError>
        </CardContent>
      </Card>
    );
  }

  if (currentUser.data?.org_id == null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle as="h1">SSO settings</CardTitle>
        </CardHeader>
        <CardContent>
          <AlertError>
            Your account is not associated with an organization, so there is no SSO
            configuration to manage.
          </AlertError>
        </CardContent>
      </Card>
    );
  }

  return <SsoConfigForm />;
}

function SsoConfigForm(): React.JSX.Element {
  const ssoConfig = useSsoConfig();
  const upsert = useUpsertSsoConfig();
  const remove = useDeleteSsoConfig();
  const deleteDialogRef = useRef<DialogHandle>(null);

  const existing = ssoConfig.data ?? null;
  const [issuer, setIssuer] = useState(existing?.issuer ?? '');
  const [clientId, setClientId] = useState(existing?.client_id ?? '');
  const [clientSecret, setClientSecret] = useState('');
  const [emailDomain, setEmailDomain] = useState(existing?.email_domain ?? '');
  const [initialized, setInitialized] = useState(false);

  // Populate the form once, when the existing config first loads — a
  // controlled re-sync on every refetch would clobber in-progress edits.
  if (!initialized && ssoConfig.isSuccess) {
    if (existing) {
      setIssuer(existing.issuer);
      setClientId(existing.client_id);
      setEmailDomain(existing.email_domain);
    }
    setInitialized(true);
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    upsert.mutate(
      { issuer, client_id: clientId, client_secret: clientSecret, email_domain: emailDomain },
      { onSuccess: () => setClientSecret('') },
    );
  };

  const confirmDelete = (): void => {
    remove.mutate(undefined, {
      onSuccess: () => {
        setIssuer('');
        setClientId('');
        setClientSecret('');
        setEmailDomain('');
        upsert.reset(); // clear a stale "saved" banner left over from before the delete
      },
    });
    deleteDialogRef.current?.close();
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">SSO settings</h1>
        <p className="text-sm text-muted-foreground">
          Let your organization&apos;s members sign in through your own identity provider
          instead of a Corveon password (OIDC, ADR-0025).
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <ShieldCheck className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          <div>
            <CardTitle>{existing ? 'Update your OIDC connection' : 'Connect an OIDC provider'}</CardTitle>
            <CardDescription>
              Okta, Azure AD, Google Workspace, or any standards-compliant OIDC provider.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            {upsert.isError && <AlertError>{upsert.error.message}</AlertError>}
            {upsert.isSuccess && (
              <AlertSuccess>SSO configuration saved.</AlertSuccess>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="issuer">Issuer URL</Label>
              <Input
                id="issuer"
                name="issuer"
                type="url"
                placeholder="https://your-org.okta.com"
                required
                value={issuer}
                onChange={(e) => setIssuer(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="client-id">Client ID</Label>
              <Input
                id="client-id"
                name="clientId"
                required
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="client-secret">Client secret</Label>
              <Input
                id="client-secret"
                name="clientSecret"
                type="password"
                autoComplete="new-password"
                required
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                aria-describedby="client-secret-hint"
              />
              <p id="client-secret-hint" className="text-xs text-muted-foreground">
                {existing
                  ? "Stored encrypted — re-enter it to change your connection, even if you're only updating another field."
                  : 'Stored encrypted, never shown again.'}
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email-domain">Email domain</Label>
              <Input
                id="email-domain"
                name="emailDomain"
                placeholder="your-org.com"
                required
                value={emailDomain}
                onChange={(e) => setEmailDomain(e.target.value)}
                aria-describedby="email-domain-hint"
              />
              <p id="email-domain-hint" className="text-xs text-muted-foreground">
                Members with an email at this domain are routed to your identity provider from
                the &quot;Sign in with SSO&quot; login option.
              </p>
            </div>

            <Button type="submit" isLoading={upsert.isPending} className="mt-2 self-start">
              {existing ? 'Save changes' : 'Connect'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {existing && (
        <Card>
          <CardHeader>
            <CardTitle>Remove SSO</CardTitle>
            <CardDescription>
              Members will sign in with a Corveon password again. Existing SSO-provisioned
              accounts are not deleted.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {remove.isError && (
              <div className="mb-3">
                <AlertError>{remove.error.message}</AlertError>
              </div>
            )}
            <Button
              variant="destructive"
              onClick={() => deleteDialogRef.current?.showModal()}
            >
              Remove SSO configuration
            </Button>
          </CardContent>
        </Card>
      )}

      <Dialog
        ref={deleteDialogRef}
        title="Remove SSO configuration?"
        description="Members at this email domain will no longer be able to sign in through your identity provider. This can't be undone."
      >
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => deleteDialogRef.current?.close()}>
            Cancel
          </Button>
          <Button variant="destructive" isLoading={remove.isPending} onClick={confirmDelete}>
            Remove
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
