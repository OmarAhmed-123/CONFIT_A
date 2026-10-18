import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { PartnerPortalBoundary } from '../AppRoutes';
import { PortalBackButton } from '../../components/navigation/PortalBackButton';
import { useAuthStore } from '../../stores/authStore';

const Path: React.FC = () => {
  const location = useLocation();
  return <output>{location.pathname}</output>;
};

const setIdentity = (role: string) => {
  useAuthStore.setState({
    user: { id: 1, email: `${role}@confit.test`, full_name: role, role } as any,
    isAuthenticated: true,
    isLoading: false,
    hasAttemptedBootstrap: true,
  });
};

beforeEach(() => setIdentity('admin'));

describe('partner/admin route separation', () => {
  it.each([
    ['/b2b', '/admin'],
    ['/b2b/catalog', '/admin/catalog'],
    ['/b2b/inventory', '/admin/catalog'],
    ['/b2b/placements', '/admin/catalog'],
    ['/b2b/analytics', '/admin/analytics'],
    ['/partner/catalog', '/admin/catalog'],
  ])('redirects an admin bookmark %s to %s without mounting partner content', (from, to) => {
    render(
      <MemoryRouter initialEntries={[from]}>
        <Routes>
          <Route
            path="/b2b/*"
            element={<PartnerPortalBoundary><p>partner tenant content</p></PartnerPortalBoundary>}
          />
          <Route
            path="/partner/*"
            element={<PartnerPortalBoundary><p>partner tenant content</p></PartnerPortalBoundary>}
          />
          <Route path="/admin/*" element={<Path />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(to)).toBeTruthy();
    expect(screen.queryByText('partner tenant content')).toBeNull();
  });

  it('still admits an authenticated brand role to its tenant portal', () => {
    setIdentity('brand_manager');
    render(
      <MemoryRouter initialEntries={['/b2b/catalog']}>
        <PartnerPortalBoundary><p>partner tenant content</p></PartnerPortalBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText('partner tenant content')).toBeTruthy();
  });
});


describe('BRD-02 tenant-membership admission', () => {
  const renderB2b = () =>
    render(
      <MemoryRouter initialEntries={['/b2b/team']}>
        <Routes>
          <Route
            path="/b2b/*"
            element={<PartnerPortalBoundary><p>partner tenant content</p></PartnerPortalBoundary>}
          />
          <Route path="/admin/*" element={<Path />} />
        </Routes>
      </MemoryRouter>,
    );

  it('admits a global-consumer account that holds an active brand membership', () => {
    useAuthStore.setState({
      user: { id: 9, email: 'invited@confit.test', full_name: 'Invited', role: 'consumer' } as any,
      isAuthenticated: true,
      isLoading: false,
      hasAttemptedBootstrap: true,
      brandMemberships: [{ brand_id: 7, brand_name: 'Atelier Noir', slug: 'atelier-noir', role: 'staff', status: 'active' }],
      brandMembershipsStatus: 'ready',
    });
    renderB2b();
    expect(screen.getByText('partner tenant content')).toBeTruthy();
  });

  it('keeps the gateway up when the resolved membership list is empty', () => {
    useAuthStore.setState({
      user: { id: 9, email: 'nobody@confit.test', full_name: 'Nobody', role: 'consumer' } as any,
      isAuthenticated: true,
      isLoading: false,
      hasAttemptedBootstrap: true,
      brandMemberships: [],
      brandMembershipsStatus: 'ready',
    });
    renderB2b();
    expect(screen.queryByText('partner tenant content')).toBeNull();
  });
});

describe('portal back navigation', () => {
  it('returns to the previous portal page when an in-app history entry exists', () => {
    render(
      <MemoryRouter initialEntries={['/admin', '/admin/audit']} initialIndex={1}>
        <PortalBackButton />
        <Path />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /go back/i }));
    expect(screen.getByText('/admin')).toBeTruthy();
  });

  it('uses the role-safe admin home fallback for a direct entry', () => {
    render(
      <MemoryRouter initialEntries={['/admin/audit']}>
        <PortalBackButton />
        <Path />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /go back/i }));
    expect(screen.getByText('/admin')).toBeTruthy();
  });
});
