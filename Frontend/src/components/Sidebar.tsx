import { NavLink } from 'react-router-dom'
import logoHEssers from '../assets/sidebar/logo-hessers.png'
import iconHome from '../assets/sidebar/icon-home.svg'
import iconHomeActive from '../assets/sidebar/icon-home-active.svg'
import iconVersionControl from '../assets/sidebar/icon-version-control.svg'
import iconVersionControlActive from '../assets/sidebar/icon-version-control-active.svg'
import avatar from '../assets/sidebar/avatar.svg'

type NavItem = {
  label: string
  to: string
  icon: string
  activeIcon: string
}

const navItems: NavItem[] = [
  { label: 'Home', to: '/', icon: iconHome, activeIcon: iconHomeActive },
  {
    label: 'Version Control',
    to: '/version-control',
    icon: iconVersionControl,
    activeIcon: iconVersionControlActive,
  },
]

function Sidebar() {
  return (
    <aside className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col gap-[6px] bg-[#a50000] px-4 py-5">
      <div className="flex flex-col items-start gap-[10px] px-2 pt-1 pb-5">
        <img src={logoHEssers} alt="H.Essers" className="h-[78px] w-[96px]" />
        <p className="font-['Montserrat',sans-serif] text-[15px] font-bold whitespace-nowrap text-white">
          AI Mapping Engine
        </p>
      </div>

      <nav className="flex flex-col gap-[6px]">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex w-full items-center gap-[10px] rounded-lg px-[10px] py-[9px] text-[14px] ${
                isActive
                  ? 'bg-white/[0.18] font-semibold text-white'
                  : 'font-medium text-white/80 hover:bg-white/10'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <img src={isActive ? item.activeIcon : item.icon} alt="" width={18} height={18} />
                <span className="flex-1 text-left">{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      <div className="flex w-full items-center gap-[10px] border-t border-white/25 px-2 py-[10px]">
        <img src={avatar} alt="" width={32} height={32} />
        <div className="flex flex-col whitespace-nowrap">
          <p className="text-[13px] font-semibold text-white">Analist A</p>
          <p className="text-[12px] text-white/75">Analist</p>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
