# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-16 17:17:09
# @Last Modified by:   nils
# @Last Modified time: 2016-05-24 22:34:19

import cmd
import os


class CLI(cmd.Cmd):
    '''
    Command Line Interface
    '''

    # Configuring Cmd Through Attributes
    prompt = '>>'
    intro = 'Inlinino 2.0 alpha (May 16, 2016)\n' + \
            'Type "help", "support", or "credits" for more information.'

    doc_header = 'List of commands available (type help <topic>):'
    # misc_header = 'misc_header'
    # undoc_header = 'undoc_header'
    # ruler = '-'

    # Member variables
    m_app = None

    # Initialize interface
    def __init__(self, _app):
        cmd.Cmd.__init__(self)
        self.m_app = _app

    # Instruments
    def do_instrument(self, line):
        if line == "":
            print('WARNING: Command instrument take an argument ' +
                  '(connect, close, or list).')
            return

        arg = line.split()
        narg = len(arg)

        if arg[0] == "connect":
            if narg != 2 and narg != 3:
                print('WARNING: ' + arg[0] + ' takes 1 or 2 arguments\n' +
                      '\t specify instrument to connect and the port (option)')
                return
            # Connect to instrument specified in arg[1]
            if arg[1] not in self.m_app.m_instruments.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('Unknown instrument')
                return
            self.m_app.m_instruments[arg[1]].Connect()
        elif arg[0] == "close":
            if narg != 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument\n' +
                      '\t specify instrument to disconnect')
                return
            # Connect to instrument specified in arg[1]
            if arg[1] not in self.m_app.m_instruments.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('Unknown instrument')
                return
            self.m_app.m_instruments[arg[1]].Close()
        elif arg[0] == 'list':
            if narg > 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument\n' +
                      '\t list ports or list instruments')
                return
            if narg < 2:
                # Display list of instruments
                foo = ''
                for inst, inst in self.m_app.m_instruments.items():
                    foo += str(inst) + '\n'
                print(foo, end='', flush=True)
            elif arg[1] == 'ports':
                # Display list of ports
                print('Listing ports')
            else:
                print('WARNING: Unknown argument ' + arg[1] + ' for list')
        else:
            print('WARNING: Unknown command ' + line)

    def complete_instrument(self, text, line, begidx, endidx):
        cmd_available = ['connect', 'close', 'list']
        if not text:
            completions = cmd_available
        else:
            completions = [f for f in cmd_available
                           if f.startswith(text)]
        return completions

    def help_instrument(self):
        print('instrument [arg]\n\t' +
              '<connect> [instrument_name] [port_name]\n\t' +
              '\tconnect to instrument using specified port\n\t' +
              '<close> [instrument_name]\n\t' +
              '\tclose connection with instrument\n\t' +
              '<list> [instruments|ports]\n\t' +
              '\tlist all instruments or ports')

    # Log
    def do_log(self, line):
        if line == "":
            print('WARNING: Command log take an argument ' +
                  '(start or stop).')
        elif line == "start":
            self.m_app.m_log_data.Start()
            print("Start logging data.")
        elif line == "stop":
            self.m_app.m_log_data.Stop()
            print("Stop logging data.")
        else:
            print('WARNING: Unknown command ' + line)

    def complete_log(self, text, line, begidx, endidx):
        cmd_available = ['start', 'stop']
        if not text:
            completions = cmd_available
        else:
            completions = [f for f in cmd_available
                           if f.startswith(text)]
        return completions

    def help_log(self):
        print('log [arg]\n\t<start> logging data\n\t<stop> logging data')

    # Status
    def do_status(self, line):
        print(self.m_app)

    def help_status(self):
        print('status\n\tDisplay some parameters and state of instruments')

    # Exit
    def do_exit(self, line):
        return self.do_EOF(line)

    def help_exit(self):
        return self.help_EOF()

    def do_EOF(self, line):
        return True

    def help_EOF(self):
        print('exit or EOF\n\t' +
              'Quit Inlinino after:\n\t' +
              '\t- closing all instrument connection\n\t' +
              '\t- stoping all logging activity\n\t' +
              'All data is saved automatically.')

    # Credits
    def do_credits(self, line):
        print('### Credits ###\n' +
              'Developped by Nils Haëntjens (University of Maine)\n' +
              'Inspired by Instrumentino from Joel Koenka\n')

    def help_credits(self):
        print('credits\n\t' +
              'Display credits\n\t')

    # Support
    def do_support(self, line):
        print('### Support ###\n' +
              'Send questions, bug reports, fixes, enhancements, t-shirts, ' +
              'money, lobsters & beers to Nils\n' +
              '<nils.haentjens+inlinino@maine.edu>')

    def help_support(self):
        print('support\n\t' +
              'Display support informations\n\t')

    # Override Cmd class methods
    def emptyline(self):
        # By default empty line re-do previous command
        # Rewrite it to do nothing
        pass

    def do_shell(self, line):
        # Run a shell command
        print(os.popen(line).read())

    def help_shell(self):
        print('! or shell\n\tRun command on host shell')


if __name__ == '__main__':
    CLI(None).cmdloop()
